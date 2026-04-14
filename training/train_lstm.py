"""LSTM Training Script — trains on real market data."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from training.progress_writer import update_training_progress

import json
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import MinMaxScaler
from loguru import logger
from Python.agi_brain import AGIModel, FEATURE_COLUMNS
from Python.feature_pipeline import build_lstm_feature_frame, ENGINEERED_V2
from Python.data_feed import fetch_training_data

CLASS_NAMES = ["LOW_VOL", "MED_VOL", "HIGH_VOL"]

# ── Logging ─────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger.add(os.path.join(LOG_DIR, "lstm_training.log"), rotation="10 MB", level="DEBUG")

def create_sequences(data, close_prices, seq_len=60):
    """Create input sequences and labels for LSTM training (Volatility Focused).

    Args:
        data: scaled feature matrix (n_samples, n_features)
        close_prices: raw close prices for label generation
        seq_len: sequence length for LSTM
    """
    X, y = [], []
    for i in range(seq_len, len(data) - 1):
        X.append(data[i - seq_len:i])

        # Calculate next return magnitude from raw close prices
        future_return = (close_prices[i] - close_prices[i - 1]) / (close_prices[i - 1] + 1e-8)
        magnitude = abs(future_return)

        # Classify based on volatility threshold
        # 0 = Low volatility (HOLD)
        # 1 = Medium volatility
        # 2 = High Volatility Spike
        if magnitude > 0.0015:
            y.append(2)  # High vol
        elif magnitude > 0.0005:
            y.append(1)  # Med vol
        else:
            y.append(0)  # Low vol/Hold

    return np.array(X), np.array(y)

def train_lstm(symbols=None, epochs=50, seq_len=60):
    if symbols is None:
        symbols = ["EURUSDm", "GBPUSDm", "XAUUSDm"]

    if torch.cuda.is_available():
        device = 'cuda'
    elif getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available():
        device = 'mps'
    else:
        device = 'cpu'
    feature_columns = list(FEATURE_COLUMNS)
    n_features = len(feature_columns)
    model = AGIModel(input_dim=n_features).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    scaler = MinMaxScaler()

    logger.success(f"LSTM Training started on {device.upper()} | Symbols: {symbols} | Epochs: {epochs} | Features: {n_features}")

    # ── Fetch and combine training data ─────────────────────────────
    all_X, all_y = [], []
    for sym in symbols:
        logger.info(f"Fetching training data for {sym}...")
        df = fetch_training_data(sym, period="60d")
        if df is None or df.empty or len(df) < seq_len + 100:
            logger.warning(f"Insufficient data for {sym} (len={0 if df is None else len(df)}), skipping")
            continue

        # Build engineered features using the feature pipeline
        feat_df, available_cols = build_lstm_feature_frame(df, feature_version=ENGINEERED_V2)
        if len(feat_df) < seq_len + 10:
            logger.warning(f"Not enough feature rows for {sym} after pipeline, skipping")
            continue

        # Use the columns the model expects
        use_cols = feature_columns if set(feature_columns).issubset(set(available_cols)) else available_cols
        features = feat_df[use_cols].astype(float).values

        # Get close prices for label generation (aligned with feature rows)
        close_prices = df["close"].iloc[-len(feat_df):].values

        data = scaler.fit_transform(features)
        X, y = create_sequences(data, close_prices, seq_len)
        all_X.append(X)
        all_y.append(y)
        logger.info(f"  {sym}: {len(X)} sequences | LOW:{(y==0).sum()} MED:{(y==1).sum()} HIGH:{(y==2).sum()}")

    if not all_X:
        logger.error("No training data available!")
        return

    X_train = np.concatenate(all_X)
    y_train = np.concatenate(all_y)
    logger.info(f"Total training set: {len(X_train)} sequences | "
                f"LOW_VOL:{(y_train==0).sum()} MED_VOL:{(y_train==1).sum()} HIGH_VOL:{(y_train==2).sum()}")

    # Convert to tensors
    X_tensor = torch.tensor(X_train, dtype=torch.float32).to(device)
    y_tensor = torch.tensor(y_train, dtype=torch.long).to(device)

    # ── Compute class weights for imbalanced dataset ──
    # Use sqrt-inverse-frequency: less aggressive than full inverse frequency
    # Prevents the model from overcompensating on minority classes
    class_counts = np.array([(y_train == i).sum() for i in range(3)], dtype=np.float64)
    total_samples = len(y_train)
    raw_weights = total_samples / (3.0 * class_counts + 1e-6)
    # Cap weights at 3x to prevent extreme overprediction of rare classes
    class_weights = np.minimum(raw_weights, 3.0)
    # Normalize so weights average to 1.0
    class_weights = class_weights / class_weights.mean()
    class_weights_tensor = torch.tensor(class_weights, dtype=torch.float32).to(device)
    logger.info(f"Class weights (capped sqrt): LOW_VOL={class_weights[0]:.3f} MED_VOL={class_weights[1]:.3f} HIGH_VOL={class_weights[2]:.3f}")

    # ── Time-aware train/val split (last 20% as validation) ──
    split_idx = int(len(X_tensor) * 0.8)
    X_train_split = X_tensor[:split_idx]
    y_train_split = y_tensor[:split_idx]
    X_val_split = X_tensor[split_idx:]
    y_val_split = y_tensor[split_idx:]
    logger.info(f"Train/val split: {len(X_train_split)} train, {len(X_val_split)} validation")

    # ── Setup with class-weighted loss and LR scheduler ──
    criterion = nn.CrossEntropyLoss(weight=class_weights_tensor)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5, min_lr=1e-6)

    # ── Early stopping ──
    best_val_loss = float('inf')
    patience_counter = 0
    patience = 7
    best_model_state = None

    # ── Training loop ───────────────────────────────────────────────
    model.train()
    batch_size = 64
    n_batches = len(X_train_split) // batch_size

    for epoch in range(epochs):
        # Shuffle each epoch
        perm = torch.randperm(len(X_train_split))
        X_train_shuf = X_train_split[perm]
        y_train_shuf = y_train_split[perm]

        epoch_loss = 0.0
        correct = 0
        total = 0

        for b in range(n_batches):
            start = b * batch_size
            end = start + batch_size
            X_batch = X_train_shuf[start:end]
            y_batch = y_train_shuf[start:end]

            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            _, predicted = outputs.max(1)
            correct += (predicted == y_batch).sum().item()
            total += y_batch.size(0)

        acc = correct / total * 100 if total > 0 else 0
        avg_loss = epoch_loss / max(n_batches, 1)

        # ── Validation evaluation ──
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_val_split)
            val_loss = nn.CrossEntropyLoss(weight=class_weights_tensor)(val_outputs, y_val_split).item()
            _, val_preds = val_outputs.max(1)
            val_acc = (val_preds == y_val_split).sum().item() / len(y_val_split) * 100

            # Per-class recall on validation set
            per_class = []
            for c in range(3):
                mask = (y_val_split == c)
                if mask.sum() > 0:
                    recall = (val_preds[mask] == c).sum().item() / mask.sum().item() * 100
                    per_class.append(f"{CLASS_NAMES[c]}:{recall:.0f}%")
                else:
                    per_class.append(f"{CLASS_NAMES[c]}:N/A")
            per_class_str = " | ".join(per_class)

            # Macro F1
            f1_scores = []
            for c in range(3):
                mask_c = (y_val_split == c)
                pred_c = (val_preds == c)
                tp = (pred_c & mask_c).sum().item()
                fp = (pred_c & ~mask_c).sum().item()
                fn = (~pred_c & mask_c).sum().item()
                prec = tp / (tp + fp + 1e-8)
                rec = tp / (tp + fn + 1e-8)
                f1 = 2 * prec * rec / (prec + rec + 1e-8)
                f1_scores.append(f1)
            macro_f1 = sum(f1_scores) / 3

        logger.info(f"Epoch {epoch+1:3d}/{epochs} | Train Loss: {avg_loss:.4f} | Train Acc: {acc:.1f}% | "
                    f"Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.1f}% | Macro F1: {macro_f1:.3f} | {per_class_str}")
        update_training_progress("lstm", {
            "running": True,
            "symbol": ",".join(symbols),
            "epoch": epoch + 1,
            "epochs_total": epochs,
            "loss": round(avg_loss, 4),
            "accuracy": round(acc, 1),
            "val_loss": round(val_loss, 4),
            "val_accuracy": round(val_acc, 1),
            "macro_f1": round(macro_f1, 4),
        })

        # ── LR scheduler and early stopping ──
        scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            patience_counter += 1
            if patience_counter >= patience:
                logger.info(f"Early stopping at epoch {epoch+1} (no val loss improvement for {patience} epochs)")
                break

        model.train()

    # ── Save model + scaler + metadata ─────────────────────────────
    model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
    os.makedirs(model_dir, exist_ok=True)

    model_path = os.path.join(model_dir, "lstm_agi_trained.pt")
    torch.save(model.state_dict(), model_path)
    logger.success(f"LSTM model saved: {model_path} ({os.path.getsize(model_path)/1024:.1f} KB)")

    scaler_path = os.path.join(model_dir, "lstm_scaler.pkl")
    joblib.dump(scaler, scaler_path)
    logger.success(f"Scaler saved: {scaler_path}")

    meta_path = os.path.join(model_dir, "lstm_agi_trained.meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "feature_columns": feature_columns,
            "feature_version": ENGINEERED_V2,
            "n_features": n_features,
            "symbols": symbols,
            "epochs": epochs,
            "seq_len": seq_len,
        }, f, indent=2)
    logger.success(f"Metadata saved: {meta_path}")

    # ── Final stats ─────────────────────────────────────────────────
    # Restore best model from early stopping
    if best_model_state is not None:
        model.load_state_dict(best_model_state)
        logger.info(f"Restored best model (val_loss={best_val_loss:.4f})")

    model.eval()
    with torch.no_grad():
        val_outputs = model(X_val_split)
        _, val_preds = val_outputs.max(1)
        final_acc = (val_preds == y_val_split).sum().item() / len(y_val_split) * 100

        # Per-class metrics
        per_class = []
        f1_scores = []
        for c in range(3):
            mask = (y_val_split == c)
            pred_c = (val_preds == c)
            tp = (pred_c & mask).sum().item()
            fp = (pred_c & ~mask).sum().item()
            fn = (~pred_c & mask).sum().item()
            prec = tp / (tp + fp + 1e-8)
            rec = tp / (tp + fn + 1e-8)
            f1 = 2 * prec * rec / (prec + rec + 1e-8)
            f1_scores.append(f1)
            per_class.append(f"{CLASS_NAMES[c]} P={prec:.2f} R={rec:.2f} F1={f1:.2f}")
        macro_f1 = sum(f1_scores) / 3
    logger.success(f"Training complete! Val accuracy: {final_acc:.1f}% | Macro F1: {macro_f1:.3f}")
    for pc in per_class:
        logger.info(f"  {pc}")
    update_training_progress("lstm", {
        "running": False,
        "symbol": ",".join(symbols),
        "epoch": epochs,
        "epochs_total": epochs,
        "loss": round(avg_loss, 4),
        "accuracy": round(final_acc, 1),
        "completed": True,
    })

    # Compute per-class metrics for scorecard
    per_class_metrics = {}
    with torch.no_grad():
        val_outputs_final = model(X_val_split)
        _, val_preds_final = val_outputs_final.max(1)
        for c in range(3):
            mask = (y_val_split == c)
            pred_c = (val_preds_final == c)
            tp = (pred_c & mask).sum().item()
            fp = (pred_c & ~mask).sum().item()
            fn = (~pred_c & mask).sum().item()
            prec = tp / (tp + fp + 1e-8)
            rec = tp / (tp + fn + 1e-8)
            f1 = 2 * prec * rec / (prec + rec + 1e-8)
            per_class_metrics[CLASS_NAMES[c]] = {"precision": float(prec), "recall": float(rec), "f1": float(f1)}

    metrics = {
        "win_rate": float(final_acc),
        "macro_f1": float(macro_f1),
        "per_class": per_class_metrics,
        "epochs": epochs,
        "loss": float(best_val_loss),
        "val_accuracy": float(final_acc),
        "date": __import__('datetime').datetime.now().isoformat()
    }
    
    # Save Candidate locally in Model Registry for autonomous evaluation loop
    try:
        from Python.model_registry import ModelRegistry
        import shutil
        reg = ModelRegistry()
        cand_path = reg.save_candidate(model.state_dict(), metrics, model_type="lstm")
        shutil.copy(scaler_path, os.path.join(cand_path, "lstm_scaler.pkl"))
        
        # Immediately Test against Champion to see if Canary Staging is permitted
        if reg.evaluate_and_stage_canary(cand_path):
            logger.success("Candidate surpassed Champion. Scheduled for live Canary testing tomorrow!")
    except Exception as e:
        logger.error(f"Failed to register candidate model: {e}")

if __name__ == "__main__":
    train_lstm(epochs=50)

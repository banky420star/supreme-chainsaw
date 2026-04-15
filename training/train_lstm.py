"""LSTM Training Script — trains on real market data with balanced sampling and Macro F1 early stopping."""
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

# Per-symbol volatility thresholds (FX pairs have tiny moves, commodities have large moves)
SYMBOL_THRESHOLDS = {
    "EURUSDm": (0.0003, 0.0008),   # MED > 0.03%, HIGH > 0.08%
    "GBPUSDm": (0.0004, 0.0010),   # MED > 0.04%, HIGH > 0.10%
    "XAUUSDm": (0.0015, 0.0040),   # MED > 0.15%, HIGH > 0.40%
    "BTCUSDm": (0.0050, 0.0150),   # MED > 0.50%, HIGH > 1.50%
}
DEFAULT_THRESHOLDS = (0.0005, 0.0015)

# ── Logging ─────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger.add(os.path.join(LOG_DIR, "lstm_training.log"), rotation="10 MB", level="DEBUG")


def _parse_symbol_currencies(symbol):
    """Parse a broker symbol into its two currency/commodity codes.
    Handles: EURUSDm -> [EUR, USD], XAUUSDm -> [XAU, USD], BTCUSDm -> [BTC, USD]
    Strips trailing lowercase broker suffixes (e.g. 'm').
    """
    base = symbol.rstrip("m").rstrip("M")
    for prefix in ["XAU", "XAG", "XPT"]:
        if base.startswith(prefix):
            return [prefix, base[len(prefix):]]
    if len(base) == 6:
        return [base[:3], base[3:]]
    for prefix in ["BTC", "ETH", "SOL", "LTC"]:
        if base.startswith(prefix):
            return [prefix, base[len(prefix):]]
    currencies = []
    for i in range(0, len(base) - 2, 3):
        currencies.append(base[i:i+3])
    return currencies if currencies else [base]


def create_sequences(data, close_prices, seq_len=60, med_thresh=0.0005, high_thresh=0.0015):
    """Create input sequences and labels for LSTM training (Volatility Focused).

    Args:
        data: scaled feature matrix (n_samples, n_features)
        close_prices: raw close prices for label generation
        seq_len: sequence length for LSTM
        med_thresh: threshold for MED_VOL label
        high_thresh: threshold for HIGH_VOL label
    """
    X, y = [], []
    for i in range(seq_len, len(data) - 1):
        X.append(data[i - seq_len:i])

        future_return = (close_prices[i] - close_prices[i - 1]) / (close_prices[i - 1] + 1e-8)
        magnitude = abs(future_return)

        if magnitude > high_thresh:
            y.append(2)  # HIGH_VOL
        elif magnitude > med_thresh:
            y.append(1)  # MED_VOL
        else:
            y.append(0)  # LOW_VOL

    return np.array(X), np.array(y)


def _balance_per_symbol(X_sym, y_sym, max_per_class=None):
    """Undersample LOW_VOL within a single symbol so classes are more balanced.
    Keeps all MED_VOL and HIGH_VOL samples, randomly samples LOW_VOL down to
    2x the largest minority class count.
    """
    counts = [(y_sym == c).sum() for c in range(3)]
    minority_max = max(counts[1], counts[2])
    if minority_max == 0:
        minority_max = counts[0] // 4
    low_cap = min(counts[0], minority_max * 2)
    if max_per_class is not None:
        low_cap = min(low_cap, max_per_class)

    low_idx = np.where(y_sym == 0)[0]
    keep_low = np.random.choice(low_idx, size=low_cap, replace=False) if len(low_idx) > low_cap else low_idx

    med_idx = np.where(y_sym == 1)[0]
    high_idx = np.where(y_sym == 2)[0]

    all_idx = np.concatenate([keep_low, med_idx, high_idx])
    np.random.shuffle(all_idx)
    return X_sym[all_idx], y_sym[all_idx]


def train_lstm(symbols=None, epochs=80, seq_len=60):
    if symbols is None:
        symbols = ["EURUSDm", "GBPUSDm", "XAUUSDm", "BTCUSDm"]

    if torch.cuda.is_available():
        device = 'cuda'
    elif getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available():
        device = 'mps'
    else:
        device = 'cpu'
    feature_columns = list(FEATURE_COLUMNS)
    n_features = len(feature_columns)
    model = AGIModel(input_dim=n_features).to(device)

    logger.success(f"LSTM Training started on {device.upper()} | Symbols: {symbols} | Epochs: {epochs} | Features: {n_features}")

    # ── Fetch per-symbol data with balanced sampling ────────────────
    all_X, all_y = [], []
    per_symbol_scalers = {}
    for sym in symbols:
        logger.info(f"Fetching training data for {sym}...")
        df = fetch_training_data(sym, period="60d")
        if df is None or df.empty or len(df) < seq_len + 100:
            logger.warning(f"Insufficient data for {sym} (len={0 if df is None else len(df)}), skipping")
            continue

        feat_df, available_cols = build_lstm_feature_frame(df, feature_version=ENGINEERED_V2)
        if len(feat_df) < seq_len + 10:
            logger.warning(f"Not enough feature rows for {sym} after pipeline, skipping")
            continue

        use_cols = feature_columns if set(feature_columns).issubset(set(available_cols)) else available_cols
        features = feat_df[use_cols].astype(float).values

        close_prices = df["close"].iloc[-len(feat_df):].values

        # Per-symbol scaler (preserves resolution for different price ranges)
        sym_scaler = MinMaxScaler()
        data = sym_scaler.fit_transform(features)
        per_symbol_scalers[sym] = sym_scaler

        # Per-symbol thresholds
        med_t, high_t = SYMBOL_THRESHOLDS.get(sym, DEFAULT_THRESHOLDS)

        X, y = create_sequences(data, close_prices, seq_len, med_thresh=med_t, high_thresh=high_t)
        logger.info(f"  {sym} raw: {len(X)} seq | LOW:{(y==0).sum()} MED:{(y==1).sum()} HIGH:{(y==2).sum()} | thresh: MED>{med_t} HIGH>{high_t}")

        # Balance within symbol: keep all minority, cap LOW_VOL
        X_bal, y_bal = _balance_per_symbol(X, y)
        logger.info(f"  {sym} balanced: {len(X_bal)} seq | LOW:{(y_bal==0).sum()} MED:{(y_bal==1).sum()} HIGH:{(y_bal==2).sum()}")

        all_X.append(X_bal)
        all_y.append(y_bal)

    if not all_X:
        logger.error("No training data available!")
        return

    X_train = np.concatenate(all_X)
    y_train = np.concatenate(all_y)
    logger.info(f"Total balanced set: {len(X_train)} seq | LOW_VOL:{(y_train==0).sum()} MED_VOL:{(y_train==1).sum()} HIGH_VOL:{(y_train==2).sum()}")

    X_tensor = torch.tensor(X_train, dtype=torch.float32).to(device)
    y_tensor = torch.tensor(y_train, dtype=torch.long).to(device)

    # ── Compute class weights ──
    class_counts = np.array([(y_train == i).sum() for i in range(3)], dtype=np.float64)
    total_samples = len(y_train)
    raw_weights = total_samples / (3.0 * class_counts + 1e-6)
    class_weights = np.minimum(raw_weights, 3.0)
    class_weights = class_weights / class_weights.mean()
    class_weights_tensor = torch.tensor(class_weights, dtype=torch.float32).to(device)
    logger.info(f"Class weights: LOW_VOL={class_weights[0]:.3f} MED_VOL={class_weights[1]:.3f} HIGH_VOL={class_weights[2]:.3f}")

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

    # ── Early stopping on Macro F1 (not val loss) ──
    best_macro_f1 = 0.0
    best_val_loss = float('inf')
    patience_counter = 0
    patience = 10
    best_model_state = None

    # ── Training loop ───────────────────────────────────────────────
    model.train()
    batch_size = 64
    n_batches = len(X_train_split) // batch_size

    for epoch in range(epochs):
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

            per_class = []
            f1_scores = []
            min_recall = 1.0
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
                recall_pct = rec * 100 if mask.sum() > 0 else 0
                per_class.append(f"{CLASS_NAMES[c]}:R={recall_pct:.0f}%")
                min_recall = min(min_recall, rec)
            macro_f1 = sum(f1_scores) / 3
            per_class_str = " | ".join(per_class)

        logger.info(f"Epoch {epoch+1:3d}/{epochs} | Loss: {avg_loss:.4f} | Acc: {acc:.1f}% | "
                    f"Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.1f}% | Macro F1: {macro_f1:.3f} | MinRecall: {min_recall:.3f} | {per_class_str}")
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

        scheduler.step(val_loss)

        # ── Early stopping on Macro F1 (primary metric) ──
        if macro_f1 > best_macro_f1:
            best_macro_f1 = macro_f1
            best_val_loss = val_loss
            patience_counter = 0
            best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
            logger.info(f"  -> New best Macro F1: {macro_f1:.4f} (val_loss={val_loss:.4f})")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                logger.info(f"Early stopping at epoch {epoch+1} (no Macro F1 improvement for {patience} epochs)")
                break

        model.train()

    # ── Save model + scalers + metadata ─────────────────────────────
    model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
    os.makedirs(model_dir, exist_ok=True)

    # Save per-symbol scalers
    scaler_dir = os.path.join(model_dir, "lstm_scalers")
    os.makedirs(scaler_dir, exist_ok=True)
    for sym, scaler in per_symbol_scalers.items():
        sym_scaler_path = os.path.join(scaler_dir, f"{sym}.pkl")
        joblib.dump(scaler, sym_scaler_path)
        logger.success(f"Scaler saved: {sym_scaler_path}")

    # Backward-compat combined scaler
    combined_scaler_path = os.path.join(model_dir, "lstm_scaler.pkl")
    last_scaler = list(per_symbol_scalers.values())[-1]
    joblib.dump(last_scaler, combined_scaler_path)

    # Restore best model
    if best_model_state is not None:
        model.load_state_dict(best_model_state)
        logger.info(f"Restored best model (Macro F1={best_macro_f1:.4f}, val_loss={best_val_loss:.4f})")

    model_path = os.path.join(model_dir, "lstm_agi_trained.pt")
    torch.save(model.state_dict(), model_path)
    logger.success(f"LSTM model saved: {model_path} ({os.path.getsize(model_path)/1024:.1f} KB)")

    meta_path = os.path.join(model_dir, "lstm_agi_trained.meta.json")
    meta_data = {
        "feature_columns": feature_columns,
        "feature_version": ENGINEERED_V2,
        "n_features": n_features,
        "symbols": symbols,
        "epochs": epochs,
        "seq_len": seq_len,
        "per_symbol_thresholds": {s: SYMBOL_THRESHOLDS.get(s, DEFAULT_THRESHOLDS) for s in symbols},
        "best_macro_f1": float(best_macro_f1),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, indent=2)
    logger.success(f"Metadata saved: {meta_path}")

    # ── Final validation metrics ─────────────────────────────────────
    model.eval()
    with torch.no_grad():
        val_outputs = model(X_val_split)
        _, val_preds = val_outputs.max(1)
        final_acc = (val_preds == y_val_split).sum().item() / len(y_val_split) * 100

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

    logger.success(f"Training complete! Val Acc: {final_acc:.1f}% | Macro F1: {macro_f1:.3f}")
    for pc in per_class:
        logger.info(f"  {pc}")
    update_training_progress("lstm", {
        "running": False,
        "symbol": ",".join(symbols),
        "epoch": epochs,
        "epochs_total": epochs,
        "loss": round(avg_loss, 4),
        "accuracy": round(final_acc, 1),
        "macro_f1": round(macro_f1, 4),
        "completed": True,
    })

    # Build per-class metrics for scorecard
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

    # Save candidate in Model Registry
    try:
        from Python.model_registry import ModelRegistry
        import shutil
        reg = ModelRegistry()
        cand_path = reg.save_candidate(model.state_dict(), metrics, model_type="lstm")
        for sym in per_symbol_scalers:
            shutil.copy(os.path.join(scaler_dir, f"{sym}.pkl"), os.path.join(cand_path, f"lstm_scaler_{sym}.pkl"))
        shutil.copy(combined_scaler_path, os.path.join(cand_path, "lstm_scaler.pkl"))

        if reg.evaluate_and_stage_canary(cand_path):
            logger.success("Candidate surpassed Champion. Scheduled for live Canary testing!")
        else:
            logger.info("Candidate did not pass canary gate — will continue training improvements.")
    except Exception as e:
        logger.error(f"Failed to register candidate model: {e}")

if __name__ == "__main__":
    train_lstm(epochs=80)
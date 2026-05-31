"""Feature engineering + quick model test on the 10k XAU M1 bars."""
import pandas as pd
import json
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error, r2_score

# Load data
test_files = list(Path('data/test').glob('xauusd_m1_10k_*.jsonl'))
latest = max(test_files, key=lambda p: p.stat().st_mtime)
data = [json.loads(line) for line in open(latest)]
df = pd.DataFrame(data)
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp').sort_index()

print("Loaded", len(df), "bars")

# === Feature Engineering ===
df['returns'] = df['close'].pct_change()
df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

# Simple features (common in the project's style)
df['sma_20'] = df['close'].rolling(20).mean()
df['sma_50'] = df['close'].rolling(50).mean()
df['ema_12'] = df['close'].ewm(span=12).mean()
df['ema_26'] = df['close'].ewm(span=26).mean()

df['rsi_14'] = 100 - (100 / (1 + df['returns'].rolling(14).apply(lambda x: (x[x>0].sum() / -x[x<0].sum()) if x[x<0].sum() != 0 else 1, raw=False)))

df['atr_14'] = (df['high'] - df['low']).rolling(14).mean()
df['volatility_20'] = df['returns'].rolling(20).std()

# Target: next bar return
df['target'] = df['returns'].shift(-1)

df = df.dropna()

print("After feature engineering:", len(df), "samples")

# === Simple Model Test ===
features = ['returns', 'sma_20', 'sma_50', 'ema_12', 'ema_26', 'rsi_14', 'atr_14', 'volatility_20']
X = df[features]
y = df['target']

print("\nFeatures used:", features)

# Time series cross validation
tscv = TimeSeriesSplit(n_splits=5)
scores = []

for train_idx, test_idx in tscv.split(X):
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    
    model = RandomForestRegressor(n_estimators=100, max_depth=6, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    
    preds = model.predict(X_test)
    mse = mean_squared_error(y_test, preds)
    r2 = r2_score(y_test, preds)
    scores.append((mse, r2))

print("\n=== TimeSeries CV Results (5 folds) ===")
for i, (mse, r2) in enumerate(scores):
    print(f"Fold {i+1}: MSE={mse:.8f}, R2={r2:.4f}")

avg_mse = np.mean([s[0] for s in scores])
avg_r2 = np.mean([s[1] for s in scores])
print(f"\nAverage MSE: {avg_mse:.8f}")
print(f"Average R2 : {avg_r2:.4f}")

# Feature importance on last fold
print("\nFeature Importances (last fold):")
importances = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
print(importances.round(4))

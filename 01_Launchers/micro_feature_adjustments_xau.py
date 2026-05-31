"""
Micro Feature Adjustments + Best Settings Search
On the current multi-timeframe XAUUSDm dataset (1m + 5m + 15m + 1h)

Goal: Find small, high-impact tweaks to feature parameters that improve results.
"""

import pandas as pd
import json
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score, mean_squared_error
from itertools import product
import warnings
warnings.filterwarnings('ignore')

print("=== MICRO FEATURE ADJUSTMENTS - BEST SETTINGS SEARCH ===\n")

# Load latest 10k 1m test data
latest = max(Path("data/test").glob("xauusd_m1_10k_*.jsonl"), key=lambda p: p.stat().st_mtime)
raw = pd.DataFrame([json.loads(line) for line in open(latest)])
raw["timestamp"] = pd.to_datetime(raw["timestamp"])
raw = raw.set_index("timestamp").sort_index()

print(f"Base data: {len(raw)} 1m bars of XAUUSDm\n")

def resample_ohlcv(df, rule):
    return df.resample(rule).agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna()

df1  = raw[["open","high","low","close","volume"]].copy()
df5  = resample_ohlcv(df1, "5min")
df15 = resample_ohlcv(df1, "15min")
df60 = resample_ohlcv(df1, "1h")

# ============================================================
# Feature builder with tunable parameters
# ============================================================
def build_mtf_features(df1, df5, df15, df60, 
                       sma_fast=20, sma_slow=50,
                       ema_fast=12, ema_slow=26,
                       rsi_period=14, atr_period=14,
                       vol_period=20,
                       higher_tf_vol_lookback=50):
    """Build multi-timeframe features with adjustable parameters."""
    
    def add_feats(df, p=""):
        df = df.copy()
        df[f"{p}ret1"]   = df.close.pct_change()
        df[f"{p}sma_fast"] = df.close.rolling(sma_fast).mean()
        df[f"{p}sma_slow"] = df.close.rolling(sma_slow).mean()
        df[f"{p}ema_fast"] = df.close.ewm(ema_fast).mean()
        df[f"{p}ema_slow"] = df.close.ewm(ema_slow).mean()
        df[f"{p}atr"]    = (df.high - df.low).rolling(atr_period).mean()
        df[f"{p}rsi"]    = 100 - (100 / (1 + df[f"{p}ret1"].rolling(rsi_period).apply(
            lambda x: x[x>0].sum() / -x[x<0].sum() if x[x<0].sum() != 0 else 1, raw=False)))
        df[f"{p}vol"]    = df[f"{p}ret1"].rolling(vol_period).std()
        return df

    d1  = add_feats(df1,  "1m_")
    d5  = add_feats(df5,  "5m_")
    d15 = add_feats(df15, "15m_")
    d60 = add_feats(df60, "1h_")

    def ctx(base, higher, p):
        a = higher.reindex(base.index, method="ffill")
        base[f"{p}trend"]  = (a.close > a[f"{p}sma_fast"]).astype(int)
        base[f"{p}volreg"] = (a[f"{p}vol"] > a[f"{p}vol"].rolling(higher_tf_vol_lookback).mean()).astype(int)
        return base

    d1 = ctx(d1, d5,  "5m_")
    d1 = ctx(d1, d15, "15m_")
    d1 = ctx(d1, d60, "1h_")

    feat_cols = [c for c in d1.columns if c not in ["open","high","low","close","volume"]]
    mtf = d1[feat_cols].copy()
    mtf["target"] = d1.close.pct_change().shift(-1)
    return mtf.dropna()

# ============================================================
# Evaluation function
# ============================================================
def evaluate_features(mtf_df, name=""):
    X = mtf_df[[c for c in mtf_df.columns if c != "target"]]
    y = mtf_df["target"]
    
    tscv = TimeSeriesSplit(n_splits=5)
    r2s, mses = [], []
    
    for tr, te in tscv.split(X):
        model = RandomForestRegressor(n_estimators=80, max_depth=6, random_state=42, n_jobs=-1)
        model.fit(X.iloc[tr], y.iloc[tr])
        preds = model.predict(X.iloc[te])
        r2s.append(r2_score(y.iloc[te], preds))
        mses.append(mean_squared_error(y.iloc[te], preds))
    
    return {
        "name": name,
        "avg_r2": np.mean(r2s),
        "std_r2": np.std(r2s),
        "avg_mse": np.mean(mses),
        "n_features": X.shape[1]
    }

# ============================================================
# MICRO ADJUSTMENT GRID
# ============================================================
print("Running micro-adjustment search...\n")

param_grid = {
    "sma_fast": [12, 20, 30],
    "sma_slow": [40, 50, 80],
    "ema_fast": [8, 12, 20],
    "ema_slow": [21, 26, 40],
    "rsi_period": [9, 14, 21],
    "atr_period": [10, 14, 20],
    "higher_tf_vol_lookback": [30, 50, 80],
}

results = []
base_params = {
    "sma_fast": 20, "sma_slow": 50,
    "ema_fast": 12, "ema_slow": 26,
    "rsi_period": 14, "atr_period": 14,
    "higher_tf_vol_lookback": 50,
}

# Baseline
base_mtf = build_mtf_features(df1, df5, df15, df60, **base_params)
base_res = evaluate_features(base_mtf, "BASELINE")
results.append(base_res)
print(f"BASELINE                    -> R2: {base_res['avg_r2']:.4f} | Features: {base_res['n_features']}")

# Micro grid search (small number of combinations for speed)
combinations = list(product(
    param_grid["sma_fast"], param_grid["sma_slow"],
    param_grid["ema_fast"], param_grid["ema_slow"],
    param_grid["rsi_period"], param_grid["atr_period"],
    param_grid["higher_tf_vol_lookback"]
))

print(f"\nTesting {len(combinations)} micro-adjustment combinations...\n")

best_r2 = -999
best_params = None
best_name = ""

for i, combo in enumerate(combinations[:25]):  # limit for speed in this session
    p = {
        "sma_fast": combo[0], "sma_slow": combo[1],
        "ema_fast": combo[2], "ema_slow": combo[3],
        "rsi_period": combo[4], "atr_period": combo[5],
        "higher_tf_vol_lookback": combo[6],
    }
    
    mtf_df = build_mtf_features(df1, df5, df15, df60, **p)
    res = evaluate_features(mtf_df, "")
    
    results.append({**p, **res})
    
    if res["avg_r2"] > best_r2:
        best_r2 = res["avg_r2"]
        best_params = p
        best_name = f"sma({p['sma_fast']}/{p['sma_slow']}) ema({p['ema_fast']}/{p['ema_slow']}) rsi{p['rsi_period']} atr{p['atr_period']} volLB{p['higher_tf_vol_lookback']}"
    
    if (i + 1) % 5 == 0:
        print(f"  Tested {i+1:2d}/25 ... current best R2: {best_r2:.4f}")

# Sort and show top results
df_res = pd.DataFrame(results)
df_res = df_res.sort_values("avg_r2", ascending=False)

print("\n" + "="*70)
print("TOP 8 BEST MICRO-ADJUSTMENT SETTINGS (by Avg R2 on next-bar prediction)")
print("="*70)
print(df_res.head(8)[["name", "avg_r2", "std_r2", "n_features"]].to_string(index=False))

print("\n" + "="*70)
print("BEST SETTING FOUND:")
print("="*70)
print(best_name)
print(f"Avg R2: {best_r2:.4f}   (Baseline was {base_res['avg_r2']:.4f})")
print(f"Improvement vs baseline: {best_r2 - base_res['avg_r2']:+.4f}")

print("\nBest parameters:")
for k, v in best_params.items():
    print(f"  {k}: {v}")

print("\nThis best setting can now be used as the new default for XAUUSDm multi-timeframe experiments.")
print("Next step: plug the best feature configuration into actual reward function testing + small PPO runs.")

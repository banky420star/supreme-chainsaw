import pandas as pd
import json
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score

print("=== MULTI-TIMEFRAME STANDARD PIPELINE (XAUUSDm) ===\n")

latest = max(Path("data/test").glob("xauusd_m1_10k_*.jsonl"), key=lambda p: p.stat().st_mtime)
raw = pd.DataFrame([json.loads(l) for l in open(latest)])
raw["timestamp"] = pd.to_datetime(raw["timestamp"])
raw = raw.set_index("timestamp").sort_index()

def resample(df, rule):
    return df.resample(rule).agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()

df1 = raw[["open","high","low","close","volume"]].copy()
df5  = resample(df1, "5min")
df15 = resample(df1, "15min")
df60 = resample(df1, "1h")

print(f"1m bars: {len(df1)} | 5m: {len(df5)} | 15m: {len(df15)} | 1h: {len(df60)}")

def add_feats(df, p=""):
    df = df.copy()
    df[f"{p}ret1"]  = df.close.pct_change()
    df[f"{p}sma20"] = df.close.rolling(20).mean()
    df[f"{p}sma50"] = df.close.rolling(50).mean()
    df[f"{p}ema12"] = df.close.ewm(12).mean()
    df[f"{p}atr14"] = (df.high - df.low).rolling(14).mean()
    df[f"{p}vol20"] = df[f"{p}ret1"].rolling(20).std()
    return df

df1  = add_feats(df1,  "1m_")
df5  = add_feats(df5,  "5m_")
df15 = add_feats(df15, "15m_")
df60 = add_feats(df60, "1h_")

def add_ctx(base, higher, p):
    a = higher.reindex(base.index, method="ffill")
    base[f"{p}trend"]  = (a.close > a[f"{p}sma20"]).astype(int)
    base[f"{p}volreg"] = (a[f"{p}vol20"] > a[f"{p}vol20"].rolling(50).mean()).astype(int)
    return base

df1 = add_ctx(df1, df5,  "5m_")
df1 = add_ctx(df1, df15, "15m_")
df1 = add_ctx(df1, df60, "1h_")

feat_cols = [c for c in df1.columns if c not in ["open","high","low","close","volume"]]
mtf = df1[feat_cols].copy()
mtf["target"] = df1.close.pct_change().shift(-1)
mtf = mtf.dropna()

print(f"Multi-timeframe features: {mtf.shape[1]-1} on {len(mtf)} samples")

def score(X, y, name):
    r2s = []
    for tr, te in TimeSeriesSplit(5).split(X):
        m = RandomForestRegressor(60, max_depth=5, random_state=42).fit(X.iloc[tr], y.iloc[tr])
        r2s.append(r2_score(y.iloc[te], m.predict(X.iloc[te])))
    print(f"{name:28s} -> Avg R2: {np.mean(r2s):.4f}")

single = [c for c in mtf.columns if c.startswith("1m_") and c != "target"]
print("\n=== Next-Bar Return Prediction ===")
score(mtf[single], mtf.target, "Single TF (1m only)")
score(mtf[[c for c in mtf.columns if c != "target"]], mtf.target, "Multi TF (1m+5m+15m+1h)")

print("\nStandard multi-timeframe pipeline (1m + 5m + 15m + 1h) is now active for XAUUSDm.")

"""Multi-timeframe feature builder (minimal fallback implementation)

This module provides a small, safe implementation of the API expected by
Python/feature_pipeline.py so CI/test collection succeeds while a full
implementation is developed.

Exports:
- build_multitimeframe_features(df1, df5, df15, df60, symbol, feature_version)
- load_best_feature_params(symbol)
- get_multitimeframe_feature_count()

The builder will primarily use the 1m frame if available and gracefully
pad the returned DataFrame to the expected width.
"""
from __future__ import annotations

from typing import Optional, Dict
import pandas as pd
import numpy as np


def load_best_feature_params(symbol: str) -> Dict:
    """Return stored/best feature params for a symbol.

    This fallback returns an empty dict. A real implementation should
    load tuned parameters per-symbol.
    """
    return {}


def get_multitimeframe_feature_count() -> int:
    """Return the expected number of features for multi-timeframe mode.

    Kept conservative to match existing single-timeframe defaults so callers
    that assume a width will continue to operate.
    """
    return 41


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    if "tick_volume" in out.columns and "volume" not in out.columns:
        out = out.rename(columns={"tick_volume": "volume"})
    if "volume" not in out.columns:
        out["volume"] = 0.0
    for col in ["open", "high", "low", "close"]:
        if col not in out.columns:
            raise ValueError(f"missing required column: {col}")
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
        out = out.dropna(subset=["time"]).sort_values("time").set_index("time")
    elif not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.RangeIndex(len(out))
    elif out.index.tz is None:
        out.index = pd.to_datetime(out.index, utc=True, errors="coerce")
    out = out.replace([np.inf, -np.inf], np.nan).ffill().bfill().dropna()
    return out


def build_multitimeframe_features(
    df1: Optional[pd.DataFrame],
    df5: Optional[pd.DataFrame],
    df15: Optional[pd.DataFrame],
    df60: Optional[pd.DataFrame],
    symbol: str,
    feature_version: str = "engineered_v2",
) -> pd.DataFrame:
    """Build a multi-timeframe feature DataFrame.

    This is a minimal, safe implementation that uses the 1m frame and
    ignores higher timeframes. It pads the feature set to a stable width to
    avoid breaking callers that expect a fixed number of columns.

    Raises ValueError if df1 is missing or empty, mirroring expected behavior
    elsewhere in the codebase.
    """
    if df1 is None or (hasattr(df1, "empty") and df1.empty):
        raise ValueError("At minimum a 1m DataFrame must be provided for MTF features")

    out = _normalize_ohlcv(df1)
    close = out["close"].astype(float)
    open_ = out["open"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    volume = out["volume"].astype(float)
    eps = 1e-12

    feats = {
        "open_rel": (open_ / (close + eps) - 1.0).astype(np.float32),
        "high_rel": (high / (close + eps) - 1.0).astype(np.float32),
        "low_rel": (low / (close + eps) - 1.0).astype(np.float32),
        "close_ret_1": close.pct_change().fillna(0.0).astype(np.float32),
        "log_volume": np.log1p(np.maximum(volume, 0.0)).astype(np.float32),
    }

    # Add simple rolling features for a few windows
    windows = [3, 5, 13]
    for w in windows:
        feats[f"ret_{w}"] = close.pct_change(w).fillna(0.0).astype(np.float32)
        ma = close.rolling(w, min_periods=1).mean()
        feats[f"close_ma_rel_{w}"] = (close / (ma + eps) - 1.0).astype(np.float32)

    feature_df = pd.DataFrame(feats, index=out.index)

    # If index is not datetime, keep as-is. Ensure finite values and pad as needed
    feature_df = feature_df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

    # Pad to expected width so downstream code that assumes a fixed number of
    # columns does not break. Pads with zeros and stable names.
    expected = get_multitimeframe_feature_count()
    while feature_df.shape[1] < expected:
        feature_df[f"pad_{feature_df.shape[1]}"] = 0.0

    return feature_df.astype(np.float32)

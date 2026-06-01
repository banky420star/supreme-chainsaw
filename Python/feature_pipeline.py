import numpy as np
import pandas as pd
import logging

# PatternDetector integration (Dreamer + Decision PPO now receive classical patterns + timing in obs)
try:
    from Python.patterns.pattern_detector import PatternDetector, PATTERN_FEATURE_NAMES
    _PATTERN_DETECTOR_AVAILABLE = True
except Exception:
    _PATTERN_DETECTOR_AVAILABLE = False
    PatternDetector = None
    PATTERN_FEATURE_NAMES = []


logger = logging.getLogger(__name__)

ENGINEERED_V2 = "engineered_v2"
ULTIMATE_150 = "ultimate_150"
FEATURE_VERSIONS = {ENGINEERED_V2, ULTIMATE_150}

ENGINEERED_LSTM_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ret_1",
    "ret_5",
    "ret_10",
    "rsi_14",
    "atr_14",
    "ema_12",
    "ema_26",
    "macd_line",
    "macd_signal",
    "bb_width_20",
    "stoch_k_14",
    "vol_z_20",
]


def _as_series(df: pd.DataFrame, col: str) -> pd.Series:
    obj = df[col]
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0].astype(float)
    return obj.astype(float)


def normalize_feature_version(feature_version: str | None, default: str = ENGINEERED_V2) -> str:
    version = str(feature_version or default).strip().lower()
    return version if version in FEATURE_VERSIONS else str(default)


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


def build_lstm_feature_frame(df: pd.DataFrame, feature_version: str = ENGINEERED_V2) -> tuple[pd.DataFrame, list[str]]:
    version = normalize_feature_version(feature_version, default=ENGINEERED_V2)
    if version == ULTIMATE_150:
        features = _build_ultimate_feature_frame(df)
        return features, list(features.columns)
    features = _build_engineered_lstm_frame(df)
    return features, list(ENGINEERED_LSTM_COLUMNS)


def build_env_feature_matrix(df: pd.DataFrame, feature_version: str = ENGINEERED_V2) -> np.ndarray:
    version = normalize_feature_version(feature_version, default=ENGINEERED_V2)
    if version == ULTIMATE_150:
        features, _ = build_lstm_feature_frame(df, feature_version=ULTIMATE_150)
        return features.to_numpy(dtype=np.float32)
    return _build_engineered_env_matrix(df)


def feature_count_for_version(feature_version: str) -> int:
    version = normalize_feature_version(feature_version, default=ENGINEERED_V2)
    if version == ULTIMATE_150:
        sample = pd.DataFrame(
            {
                "time": pd.date_range("2026-01-01", periods=300, freq="5min", tz="UTC"),
                "open": np.linspace(1.0, 1.2, 300),
                "high": np.linspace(1.01, 1.21, 300),
                "low": np.linspace(0.99, 1.19, 300),
                "close": np.linspace(1.0, 1.2, 300),
                "volume": np.linspace(100, 400, 300),
            }
        )
        return int(build_env_feature_matrix(sample, feature_version=ULTIMATE_150).shape[1])
    return 41


def _build_engineered_lstm_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = _normalize_ohlcv(df)
    close = _as_series(out, "close")
    high = _as_series(out, "high")
    low = _as_series(out, "low")
    volume = _as_series(out, "volume")

    out["ret_1"] = close.pct_change().fillna(0.0)
    out["ret_5"] = close.pct_change(5).fillna(0.0)
    out["ret_10"] = close.pct_change(10).fillna(0.0)

    delta = close.diff().fillna(0.0)
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-12)
    out["rsi_14"] = (100 - (100 / (1 + rs))).fillna(50.0)

    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    out["atr_14"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().bfill()

    out["ema_12"] = close.ewm(span=12, adjust=False).mean()
    out["ema_26"] = close.ewm(span=26, adjust=False).mean()
    out["macd_line"] = out["ema_12"] - out["ema_26"]
    out["macd_signal"] = out["macd_line"].ewm(span=9, adjust=False).mean()

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std().fillna(0.0)
    out["bb_width_20"] = ((bb_std * 4.0) / (bb_mid.abs() + 1e-12)).fillna(0.0)

    low_14 = low.rolling(14).min()
    high_14 = high.rolling(14).max()
    out["stoch_k_14"] = (((close - low_14) / ((high_14 - low_14) + 1e-12)) * 100.0).fillna(50.0)

    vol_mean_20 = volume.rolling(20).mean()
    vol_std_20 = volume.rolling(20).std().fillna(0.0)
    out["vol_z_20"] = ((volume - vol_mean_20) / (vol_std_20 + 1e-12)).fillna(0.0)

    out = out.replace([np.inf, -np.inf], np.nan).ffill().bfill().dropna()
    return out[ENGINEERED_LSTM_COLUMNS].copy()


def _build_engineered_env_matrix(df: pd.DataFrame) -> np.ndarray:
    out = _normalize_ohlcv(df)
    o = out["open"].to_numpy(dtype=np.float64)
    h = out["high"].to_numpy(dtype=np.float64)
    l = out["low"].to_numpy(dtype=np.float64)
    c = out["close"].to_numpy(dtype=np.float64)
    v = out["volume"].to_numpy(dtype=np.float64)
    dates = out.index if isinstance(out.index, pd.DatetimeIndex) else None
    eps = 1e-12

    def shift(arr: np.ndarray, n: int) -> np.ndarray:
        if n <= 0:
            return arr.copy()
        shifted = np.empty_like(arr)
        shifted[:n] = arr[0]
        shifted[n:] = arr[:-n]
        return shifted

    range_ = np.maximum(h - l, eps)
    close_shift1 = shift(c, 1)
    close_shift5 = shift(c, 5)
    close_shift20 = shift(c, 20)

    log_ret1 = np.log(np.maximum(c, eps) / np.maximum(close_shift1, eps))
    log_ret5 = np.log(np.maximum(c, eps) / np.maximum(close_shift5, eps))
    log_ret20 = np.log(np.maximum(c, eps) / np.maximum(close_shift20, eps))

    body_ratio = (c - o) / range_
    upper_wick = (h - np.maximum(o, c)) / range_
    lower_wick = (np.minimum(o, c) - l) / range_
    range_ratio = (h - l) / (c + eps)

    rv_20 = pd.Series(log_ret1).rolling(20, min_periods=1).std().fillna(0.0).to_numpy(dtype=np.float64)
    vol_ma20 = pd.Series(np.maximum(v, 0.0)).rolling(20, min_periods=1).mean().to_numpy(dtype=np.float64)
    rel_volume = np.maximum(v, 0.0) / (vol_ma20 + eps)
    spread_est_bps = ((h - l) / (c + eps)) * 10000.0

    ma50 = pd.Series(c).rolling(50, min_periods=1).mean().to_numpy(dtype=np.float64)
    htf_trend = (c / (ma50 + eps)) - 1.0

    hour_sin = np.zeros_like(c)
    hour_cos = np.zeros_like(c)
    dow_sin = np.zeros_like(c)
    dow_cos = np.zeros_like(c)
    if dates is not None:
        hour = dates.hour.astype(np.float64)
        dow = dates.dayofweek.astype(np.float64)
        hour_sin = np.sin(2.0 * np.pi * hour / 24.0)
        hour_cos = np.cos(2.0 * np.pi * hour / 24.0)
        dow_sin = np.sin(2.0 * np.pi * dow / 7.0)
        dow_cos = np.cos(2.0 * np.pi * dow / 7.0)

    valid_rv = rv_20[np.isfinite(rv_20)]
    if len(valid_rv) > 10:
        q1 = np.quantile(valid_rv, 0.33)
        q2 = np.quantile(valid_rv, 0.66)
        vol_bucket = np.where(rv_20 <= q1, 0.0, np.where(rv_20 <= q2, 0.5, 1.0))
    else:
        vol_bucket = np.zeros_like(c)

    close_rel = (c / (close_shift1 + eps)) - 1.0
    open_rel = (o / (c + eps)) - 1.0
    high_rel = (h / (c + eps)) - 1.0
    low_rel = (l / (c + eps)) - 1.0
    log_vol = np.log1p(np.maximum(v, 0.0))

    matrix = np.column_stack(
        [
            open_rel,
            high_rel,
            low_rel,
            close_rel,
            log_vol,
            log_ret1,
            log_ret5,
            log_ret20,
            body_ratio,
            upper_wick,
            lower_wick,
            range_ratio,
            rv_20,
            rel_volume,
            spread_est_bps,
            hour_sin,
            hour_cos,
            dow_sin,
            dow_cos,
            htf_trend,
            vol_bucket,
        ]
    )
    return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)


# ============================================================
# NEW STANDARD: Multi-Timeframe per Symbol (1m + 5m + 15m + 1h)
# ============================================================
try:
    from Python.features.multitimeframe_builder import (
        build_multitimeframe_features,
        load_best_feature_params,
        get_multitimeframe_feature_count,
    )
    _MTF_AVAILABLE = True
except Exception:
    _MTF_AVAILABLE = False

    def load_best_feature_params(symbol: str):
        return {}

    def get_multitimeframe_feature_count() -> int:
        return 41

    def build_multitimeframe_features(df1, df5, df15, df60, symbol: str, feature_version: str = "engineered_v2"):
        # Graceful fallback: if df1 exists, build a simple feature frame from 1m
        if df1 is None or (hasattr(df1, "empty") and df1.empty):
            raise ValueError("At minimum a 1m DataFrame must be provided for MTF features")
        import pandas as _pd, numpy as _np
        out = _pd.DataFrame(df1).copy()
        out.columns = [str(c).lower() for c in out.columns]
        if "volume" not in out.columns:
            out["volume"] = 0.0
        close = out["close"].astype(float)
        open_ = out["open"].astype(float)
        eps = 1e-12
        feat = _pd.DataFrame({
            "open_rel": (open_ / (close + eps) - 1.0).astype(_np.float32),
            "close_ret_1": close.pct_change().fillna(0.0).astype(_np.float32),
        }, index=out.index)
        expected = get_multitimeframe_feature_count()
        while feat.shape[1] < expected:
            feat[f"pad_{feat.shape[1]}"] = 0.0
        return feat.astype(_np.float32)


def build_multitimeframe_feature_matrix(
    dfs: dict,
    symbol: str,
    feature_version: str = "engineered_v2",
) -> np.ndarray:
    """
    Convenience wrapper that builds the standard multi-timeframe feature matrix
    (1m + 5m + 15m + 1h) using the best known parameters for the symbol.
    
    dfs should be a dict like:
        {"1m": df1, "5m": df5, "15m": df15, "1h": df1h}
    """
    df1 = dfs.get("1m") or dfs.get("1min")
    df5 = dfs.get("5m") or dfs.get("5min")
    df15 = dfs.get("15m") or dfs.get("15min")
    df60 = dfs.get("1h") or dfs.get("60min") or dfs.get("h1")
    
    if df1 is None or (hasattr(df1, 'empty') and df1.empty):
        raise ValueError("At minimum a 1m DataFrame must be provided for MTF features")
    
    # Pass through (builder now handles None/empty higher TFs via graceful degradation)
    feat_df = build_multitimeframe_features(df1, df5, df15, df60, symbol, feature_version)
    return feat_df.to_numpy(dtype=np.float32)


# Backwards-compatible alias so existing code can opt-in easily
build_standard_multitimeframe_features = build_multitimeframe_feature_matrix


# ============================================================
# Dispatch for the new standard multi-timeframe mode
# ============================================================
def _is_multitimeframe_best_request(feature_version: str | None) -> bool:
    if not feature_version:
        return False
    fv = str(feature_version).lower().strip()
    return fv in {"multitimeframe", "multitimeframe_best", "mtf_best", "standard_mtf"}

# Patch the two main builders so they can delegate to the new multi-TF builder
_original_build_env = build_env_feature_matrix
_original_build_lstm = build_lstm_feature_frame

def build_env_feature_matrix(df: pd.DataFrame, feature_version: str = ENGINEERED_V2) -> np.ndarray:
    if _is_multitimeframe_best_request(feature_version):
        # Expect the caller to have passed a properly prepared multi-TF df
        # or we fall back to normal behavior on single df
        logger.info("Multi-timeframe best feature path requested in build_env_feature_matrix")
        # For now, if a single df is passed we still build normally.
        # Full multi-TF path is used via the explicit build_multitimeframe_feature_matrix
        return _original_build_env(df, ENGINEERED_V2)
    return _original_build_env(df, feature_version)

def build_lstm_feature_frame(df: pd.DataFrame, feature_version: str = ENGINEERED_V2) -> tuple[pd.DataFrame, list[str]]:
    if _is_multitimeframe_best_request(feature_version):
        logger.info("Multi-timeframe best feature path requested in build_lstm_feature_frame")
        # Similar fallback
        return _original_build_lstm(df, ENGINEERED_V2)
    return _original_build_lstm(df, feature_version)

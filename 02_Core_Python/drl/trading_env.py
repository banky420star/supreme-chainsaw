import datetime
import json
import os
from collections import deque

import gymnasium as gym
import numpy as np
import polars as pl
import pandas as pd
from gymnasium import spaces
from Python.feature_pipeline import ENGINEERED_V2, build_env_feature_matrix, feature_count_for_version

# MTF support (new standard pipeline) - lazy to avoid circulars / optional
try:
    from Python.features.multitimeframe_builder import build_multitimeframe_features, load_best_feature_params
    from Python.data_feed import fetch_multitimeframe_training_data
    _HAS_MTF_BUILDER = True
except Exception:
    _HAS_MTF_BUILDER = False
    build_multitimeframe_features = None
    load_best_feature_params = None

# ALIGNMENT FIX (TRAINING_OBJECTIVE_ALIGNMENT_AUDIT + TRAINING_TO_PROMOTION_ALIGNMENT_REPORT):
# Added realistic slippage + strengthened drawdown tail penalty to address weak live-risk modeling.
# Long-term target: delegate core reward to Python.rewards.reward_function.TradingReward (currently unused).
# This change + follow-ups (OOS splits, real per-symbol metrics, scorecard persistence, unified strict gates)
# ensure training optimizes for production survival, not just in-sample shaped reward.
from Python.rewards.reward_function import TradingReward


# Reward Scale & Signal Improvement (v5/v6+): explicit scaling wrapper for normalization + optional lighter penalties.
# Low-risk, opt-in via env/config; defaults=1.0 preserve full hardened risk modeling exactly.
# Can be used standalone around any gym env for post-processing, or integrated (as done in TradingEnv).
class RewardScalingWrapper(gym.Wrapper):
    """Simple reward scaling + optional penalty-aware scaling wrapper.

    Usage in launchers / custom training (example):
        base_env = TradingEnv(...)
        env = RewardScalingWrapper(base_env, reward_scale=0.1, penalty_scale=0.4)
    VecNormalize (already used in training) provides additional running norm.
    Does not affect post-alignment evaluation gates (which use equity curves, not training rewards).
    """

    def __init__(self, env, reward_scale: float = 1.0, penalty_scale: float = 1.0):
        super().__init__(env)
        self.reward_scale = float(reward_scale)
        self.penalty_scale = float(penalty_scale)

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)
        # Global scale applied to whatever the inner env emitted (after its internal penalty_scale if any)
        scaled_reward = float(reward) * self.reward_scale
        # Note: for full penalty separation would require info components; here global post-scale is safe/low-risk.
        return obs, scaled_reward, terminated, truncated, info

ENGINEERED_FEATURE_COUNT = 21
DEFAULT_PORTFOLIO_FEATURE_COUNT = 3
MAX_PORTFOLIO_FEATURE_COUNT = 6

# ============================================================
# DECISION PPO RICH ACTION SPACE (high-level autonomous brain)
# ============================================================
# The Decision PPO is the "what trade to do" brain. It outputs a
# complete, executable trade specification.
# Lower-level executors (Python order_manager / MQL5 ChainGambler)
# handle actual placement, OCO, monitoring, partials, etc.
#
# Action vector is continuous Box (DECISION_ACTION_DIM,). decode_action
# maps it into a rich structured dict (DecisionSpec) consumed by:
#   - TradingEnv simulation for end-to-end reward on realized P&L/risk
#   - action_translator / execution layers -> JSON command for MQL5/Python
#   - TrainingReward integration (hold time, risk utilization, etc.)
#
# Legacy 1/3/6-dim actions remain fully supported for backward compat.
# New Decision PPO uses >=8 dims (recommended 18 for full expressivity).

DECISION_ACTION_DIM = 18  # Rich decision vector dimensionality for Decision PPO
LEGACY_ACTION_DIMS = (1, 3, 6)


class DecisionSpec:
    """
    Structured, serializable trade decision specification.
    This is the canonical output of a Decision PPO policy head.
    JSON-serializable for handoff to any executor (MQL5, Python, etc).
    """

    def __init__(self, **kwargs):
        # Core
        self.direction: float = float(kwargs.get("direction", 0.0))  # -1 sell ... +1 buy
        self.confidence: float = float(kwargs.get("confidence", 0.5))

        # Lot / Position Sizing (risk-aware, volatility targeting)
        self.lot_spec: dict = kwargs.get("lot_spec") or {
            "mode": "risk_based",  # "fixed", "risk_based", "vol_target"
            "risk_pct_equity": 0.005,  # 0.5% risk per trade default
            "fixed_lots": 0.01,
            "vol_target_pct": 0.01,  # target vol contribution
            "atr_mult_for_size": 1.0,
        }

        # Entry
        self.entry: dict = kwargs.get("entry") or {
            "type": "market",  # market | limit | stop
            "offset_pct": 0.0,
            "price": None,
        }

        # Take Profit (flexible units)
        self.tp: dict = kwargs.get("tp") or {
            "type": "pct",  # "pct" | "atr" | "price" | "rr"
            "value": 0.008,  # 0.8% or 1.5*ATR or absolute price or RR 2.0
            "rr": 2.0,
            "atr_period": 14,
        }

        # Stop Loss
        self.sl: dict = kwargs.get("sl") or {
            "type": "pct",
            "value": 0.004,
            "atr_period": 14,
            "rr": 1.0,
        }

        # Trailing Stop (rich)
        self.trailing: dict = kwargs.get("trailing") or {
            "enabled": False,
            "type": "pct",  # pct | atr | price
            "distance": 0.002,
            "step": 0.001,
            "activation_trigger_pct_or_atr": 0.003,
            "atr_mult": 1.5,
        }

        # Partial Close Logic (multiple levels)
        self.partial_close: dict = kwargs.get("partial_close") or {
            "enabled": False,
            "levels": [  # list of {trigger_*, close_pct_of_position, move_sl?, ...}
                {"trigger_profit_pct": 0.005, "close_pct": 0.50, "move_sl_to_be": True},
            ],
            "on_atr_multiple": None,
            "on_time_bars": None,
        }

        # Full close / exit conditions (beyond SL/TP)
        self.full_close: dict = kwargs.get("full_close") or {
            "max_hold_bars": 240,  # time-based exit
            "max_hold_minutes": None,
            "force_eod": False,
            "volatility_exit_atr_mult": None,  # e.g. 3.0 -> exit on spike
            "news_blackout": False,
        }

        # Breakeven logic (separate from trailing)
        self.breakeven: dict = kwargs.get("breakeven") or {
            "enabled": True,
            "trigger_fav_pct": 0.002,  # or atr
            "lock_profit_pct": 0.0,  # 0 = pure BE; >0 locks some profit
            "type": "pct",
        }

        # Risk / meta
        self.risk: dict = kwargs.get("risk") or {
            "max_risk_per_trade_pct": 0.01,
            "position_size_cap_lots": 5.0,
        }

        self.raw_action: list | None = kwargs.get("raw_action")
        self.legacy: bool = kwargs.get("legacy", False)
        self.action_version: str = kwargs.get("action_version", "decision_ppo_v1")

    def to_dict(self) -> dict:
        """Return clean JSON-serializable dict for executor consumption."""
        return {
            "direction": self.direction,
            "confidence": self.confidence,
            "lot_spec": dict(self.lot_spec),
            "entry": dict(self.entry),
            "tp": dict(self.tp),
            "sl": dict(self.sl),
            "trailing": dict(self.trailing),
            "partial_close": dict(self.partial_close),
            "full_close": dict(self.full_close),
            "breakeven": dict(self.breakeven),
            "risk": dict(self.risk),
            "legacy": self.legacy,
            "action_version": self.action_version,
            "raw_action": self.raw_action,
        }

    def to_json(self, indent: int | None = None) -> str:
        import json as _json

        return _json.dumps(self.to_dict(), indent=indent, default=float)

    @classmethod
    def from_dict(cls, d: dict) -> "DecisionSpec":
        return cls(**d)

    def __repr__(self):
        return f"DecisionSpec(dir={self.direction:.2f}, lot_mode={self.lot_spec.get('mode')}, tp={self.tp}, legacy={self.legacy})"


def _discretize_type(raw: float, types: list[str]) -> str:
    """Map [-1,1] continuous to discrete choice for type fields."""
    if not types:
        return types[0] if types else "pct"
    idx = int(np.clip((raw + 1.0) * 0.5 * (len(types) - 1e-9), 0, len(types) - 1))
    return types[idx]



class TradingEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        df=None,
        initial_balance: float = 10000.0,
        commission_rate: float = 0.0002,
        spread_bps: float = 2.0,
        slippage_bps: float = 2.5,  # ALIGNMENT FIX: realistic default (was 0); callers should override per-symbol for BTC/XAU (8-15+ bps)
        max_drawdown: float = 0.15,
        window_size: int = 100,
        max_leverage: float = 1.0,
        reward_weights: dict | None = None,
        trade_memory: dict | None = None,
        portfolio_feature_count: int | None = None,
        feature_version: str = ENGINEERED_V2,
        action_config: dict | None = None,
        symbol: str | None = None,
        reward_scale: float = 1.0,  # NEW: Reward Scale & Signal Improvement (v5+)
        penalty_scale: float = 1.0,  # NEW: <1.0 enables lighter penalty profiles for early training stability (opt-in)
    ):
        super().__init__()
        self.initial_balance = float(initial_balance)
        self.commission_rate = float(commission_rate)
        self.spread_bps = float(spread_bps)
        self.slippage_bps = float(slippage_bps)
        self.max_drawdown = float(max_drawdown)
        self.window_size = int(window_size)
        self.max_leverage = float(max_leverage)
        self.feature_version = str(feature_version or ENGINEERED_V2)
        self.symbol = str(symbol or "")
        self.action_version = "multi_trade_v1"
        self.trade_memory = trade_memory or {}
        self.mtf_dfs: dict | None = None  # for Decision PPO + new standard MTF pipeline

        w = reward_weights or {}
        self.reward_weights = {
            "growth": float(w.get("growth", 8.0)),
            "payoff": float(w.get("payoff", 2.0)),
            "sharpe_bonus": float(w.get("sharpe_bonus", 1.0)),
            "drawdown_penalty": float(w.get("drawdown_penalty", 8.0)),  # ALIGNMENT: raised from 3.0 per audit (stronger live DD control)
            "cost_penalty": float(w.get("cost_penalty", 5.0)),
            "churn_penalty": float(w.get("churn_penalty", 0.5)),
            "memory_expectancy_bonus": float(w.get("memory_expectancy_bonus", 0.5)),
            "loss_streak_penalty": float(w.get("loss_streak_penalty", 0.4)),
            "directional_followthrough": float(w.get("directional_followthrough", 0.0)),
            "actionable_target_bonus": float(w.get("actionable_target_bonus", 0.0)),
            "neutral_collapse_penalty": float(w.get("neutral_collapse_penalty", 0.0)),
        }

        # NEW: Reward Scale & Signal Improvement - env flags + profile for v5/v6 launcher flexibility
        # Defaults (1.0) = zero behavior change, full hardened preserved. Gates use realized equity (unaffected).
        self.reward_scale = float(reward_scale)
        self.penalty_scale = float(penalty_scale)
        # Env var overrides (highest precedence, for launchers without code change)
        try:
            env_rs = os.environ.get("AGI_REWARD_SCALE")
            if env_rs is not None:
                self.reward_scale = float(env_rs)
        except Exception:
            pass
        try:
            env_ps = os.environ.get("AGI_PENALTY_SCALE")
            if env_ps is not None:
                self.penalty_scale = float(env_ps)
        except Exception:
            pass
        # Optional profile for early training (lighter penalties without touching weights)
        profile = str(os.environ.get("AGI_REWARD_PROFILE", "")).strip().lower()
        if profile and os.environ.get("AGI_PENALTY_SCALE") is None:
            if profile in ("light", "early", "curriculum", "soft"):
                self.penalty_scale = 0.25
            elif profile in ("medium", "mid", "balanced"):
                self.penalty_scale = 0.5
            # "hardened", "full", "" or default -> 1.0 (preserves post-alignment hardening)

        # Instantiate the strong TradingReward (from audit - previously completely unused by training path)
        self.trading_reward = TradingReward(
            commission_rate=self.commission_rate,
            spread_bps=self.spread_bps,
            slippage_bps=self.slippage_bps,
            drawdown_penalty_coeff=self.reward_weights["drawdown_penalty"],
            overtrading_penalty_coeff=self.reward_weights.get("churn_penalty", 0.5),
            risk_violation_penalty_coeff=10.0,
            penalty_scale=self.penalty_scale,  # NEW: wired for lighter early profiles (default 1.0 = hardened)
        )
        ac = action_config or {}
        self.action_config = {
            "min_direction_abs": float(ac.get("min_direction_abs", 0.03)),
            "min_size_abs": float(ac.get("min_size_abs", 0.03)),
            "min_target_abs": float(ac.get("min_target_abs", 0.03)),
            "neutral_target_epsilon": float(ac.get("neutral_target_epsilon", ac.get("min_target_abs", 0.03))),
            "neutral_return_floor": float(ac.get("neutral_return_floor", 0.0006)),
            # Decision PPO extensions
            "decision_ppo": bool(ac.get("decision_ppo", False)),
            "decision_action_dim": int(ac.get("decision_action_dim", DECISION_ACTION_DIM)),
            "min_risk_pct": float(ac.get("min_risk_pct", 0.001)),
            "max_risk_pct": float(ac.get("max_risk_pct", 0.03)),
        }
        self.decision_ppo = self.action_config["decision_ppo"]
        self.decision_action_dim = self.action_config["decision_action_dim"]

        os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
        self.profit_log_path = os.path.join(os.getcwd(), "logs", "profitability.jsonl")
        self.breakeven_trigger_pct = float(os.environ.get("AGI_BREAKEVEN_TRIGGER_PCT", "0.002"))
        self.trailing_trigger_pct = float(os.environ.get("AGI_TRAILING_TRIGGER_PCT", "0.003"))
        self.trailing_distance_pct = float(os.environ.get("AGI_TRAILING_DISTANCE_PCT", "0.002"))
        self.trailing_step_pct = float(os.environ.get("AGI_TRAILING_STEP_PCT", "0.001"))

        # Stronger default caution around news and major market opens when using Decision PPO
        # (directly supports user's request to have the bot intelligently handle these events)
        self.news_avoidance_hold_minutes = int(os.environ.get("AGI_NEWS_AVOIDANCE_MINUTES", "25"))
        self.open_volatility_hold_minutes = int(os.environ.get("AGI_OPEN_VOL_HOLD_MINUTES", "45"))
        # Capped at 5000 entries to prevent memory growth in long-running sessions
        self.equity_curve = deque(maxlen=5000)
        self._trade_metrics = {}
        self.memory_features = self._build_memory_features(self.trade_memory)
        self.max_portfolio_features = MAX_PORTFOLIO_FEATURE_COUNT
        if portfolio_feature_count is not None:
            self.portfolio_feature_count = min(int(portfolio_feature_count), self.max_portfolio_features)
        else:
            self.portfolio_feature_count = self._default_portfolio_feature_count()

        self.n_features = 0
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32)
        act_dim = 6
        if self.decision_ppo:
            act_dim = max(8, self.decision_action_dim)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(act_dim,), dtype=np.float32)
        self.action_version = "decision_ppo_v1" if self.decision_ppo else "multi_trade_v1"

        if df is not None:
            self._set_data(df)
        else:
            self._use_synthetic()

        # Decision PPO + MTF note: callers using new standard pipeline (training/train_drl)
        # can pass feature_version="multitimeframe_best" + prebuilt features externally.
        # Full MTF obs injection supported via set_mtf_features() or future _set_data extension.

    @staticmethod
    def _safe_div(a, b):
        return a / (b + 1e-12)

    @staticmethod
    def _shift(arr: np.ndarray, n: int) -> np.ndarray:
        if n <= 0:
            return arr.copy()
        out = np.empty_like(arr)
        out[:n] = arr[0]
        out[n:] = arr[:-n]
        return out

    @staticmethod
    def _rolling_mean(arr: np.ndarray, win: int) -> np.ndarray:
        return pd.Series(arr).rolling(win, min_periods=1).mean().to_numpy(dtype=np.float64)

    @staticmethod
    def _rolling_std(arr: np.ndarray, win: int) -> np.ndarray:
        return pd.Series(arr).rolling(win, min_periods=1).std().fillna(0.0).to_numpy(dtype=np.float64)

    @staticmethod
    def _compute_atr_series(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """Simple ATR approximation (TR rolling mean)."""
        if len(high) != len(low) or len(high) != len(close):
            period = max(5, min(30, period))
            return np.full(len(high), 0.0005, dtype=np.float64)
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr = pd.Series(tr).rolling(period, min_periods=1).mean().to_numpy(dtype=np.float64)
        atr = np.nan_to_num(atr, nan=0.0005)
        return np.maximum(atr, 1e-8)

    def _build_memory_features(self, memory: dict) -> dict:
        m = memory if isinstance(memory, dict) else {}
        win_rate = float(m.get("win_rate", 50.0))
        expectancy = float(m.get("expectancy", 0.0))
        avg_loss = abs(float(m.get("avg_loss", 0.0)))
        if avg_loss < 1e-6:
            avg_loss = 1.0
        recent_loss_streak = int(m.get("recent_loss_streak", 0))
        trades = int(m.get("trades", 0))
        losses = int(m.get("losses", 0))
        loss_ratio = float(losses / max(1, trades))
        return {
            "win_rate_norm": float(np.clip((win_rate / 50.0) - 1.0, -1.0, 1.0)),
            "expectancy_norm": float(np.tanh(expectancy / avg_loss)),
            "loss_streak_norm": float(np.clip(recent_loss_streak / 10.0, 0.0, 1.0)),
            "loss_ratio_norm": float(np.clip((loss_ratio * 2.0) - 1.0, -1.0, 1.0)),
        }

    def _default_portfolio_feature_count(self) -> int:
        raw = os.environ.get("AGI_PORTFOLIO_FEATURE_COUNT", str(DEFAULT_PORTFOLIO_FEATURE_COUNT))
        try:
            count = int(raw)
        except Exception:
            count = DEFAULT_PORTFOLIO_FEATURE_COUNT
        return max(0, min(self.max_portfolio_features, count))

    @staticmethod
    def infer_portfolio_feature_count(
        obs_dim: int | None,
        window_size: int = 100,
        n_features: int = ENGINEERED_FEATURE_COUNT,
        default: int = DEFAULT_PORTFOLIO_FEATURE_COUNT,
        max_features: int = MAX_PORTFOLIO_FEATURE_COUNT,
    ) -> int:
        if obs_dim is None:
            return default
        residual = int(obs_dim) - int(window_size) * int(n_features)
        if 0 <= residual <= max_features:
            return residual
        return default

    @staticmethod
    def decode_action(
        action,
        max_leverage: float = 1.0,
        min_direction_abs: float = 0.03,
        min_size_abs: float = 0.03,
        min_target_abs: float = 0.03,
        decision_ppo: bool = False,
        decision_action_dim: int = DECISION_ACTION_DIM,
    ) -> dict:
        """
        Decode raw policy action vector into rich decision metadata + DecisionSpec.
        Supports legacy (1/3/6 dim) + full Decision PPO rich vector (>=8 dims).
        Always returns flat dict for backward compat + 'decision_spec' key (DecisionSpec instance + .to_dict()).
        """
        raw = np.asarray(action, dtype=np.float32).reshape(-1)
        n = raw.size

        # --- LEGACY PATHS (preserve exact previous behavior) ---
        if n <= 1:
            target = float(np.clip(raw[0] if n else 0.0, -1.0, 1.0)) * float(max_leverage)
            if abs(target) < float(min_target_abs):
                target = 0.0
            legacy_meta = {
                "direction": float(np.clip(target / max(float(max_leverage), 1e-12), -1.0, 1.0)),
                "size": float(min(1.0, abs(target) / max(float(max_leverage), 1e-12))),
                "risk": 1.0,
                "target": float(target),
                "legacy": True,
                "action_version": "legacy_v1",
            }
            legacy_meta["decision_spec"] = DecisionSpec(direction=legacy_meta["direction"], lot_spec={"mode": "fixed", "fixed_lots": legacy_meta["size"]}, legacy=True, action_version="legacy_v1", raw_action=raw.tolist())
            return legacy_meta

        if n == 3:
            direction_raw = float(np.clip(raw[0], -1.0, 1.0))
            size_raw = float(np.clip(raw[1], -1.0, 1.0))
            risk_raw = float(np.clip(raw[2], -1.0, 1.0))

            size = float(np.clip((size_raw + 1.0) * 0.5, 0.0, 1.0))
            risk = float(np.clip((risk_raw + 1.0) * 0.5, 0.0, 1.0))
            target = float(np.clip(direction_raw * size, -1.0, 1.0) * float(max_leverage))
            tp_sl_offset_pct = float(0.005 + risk * 0.015)

            if abs(direction_raw) < float(min_direction_abs) or size < float(min_size_abs) or abs(target) < float(min_target_abs):
                target = 0.0

            meta = {
                "direction": direction_raw,
                "size": size,
                "risk": risk,
                "target": float(target),
                "entry_mode": "market",
                "entry_offset_pct": 0.0,
                "tp_offset_pct": tp_sl_offset_pct,
                "sl_offset_pct": tp_sl_offset_pct,
                "legacy": True,
                "action_version": "legacy_v2_3d",
            }
            meta["decision_spec"] = DecisionSpec(
                direction=direction_raw,
                lot_spec={"mode": "risk_based", "risk_pct_equity": float(np.clip(risk, 0.001, 0.05))},
                entry={"type": "market"},
                tp={"type": "pct", "value": tp_sl_offset_pct},
                sl={"type": "pct", "value": tp_sl_offset_pct},
                legacy=True,
                action_version="legacy_v2_3d",
                raw_action=raw.tolist(),
            )
            return meta

        if n == 6 and not decision_ppo:
            direction_raw = float(np.clip(raw[0], -1.0, 1.0))
            size_raw = float(np.clip(raw[1], -1.0, 1.0))
            entry_mode_raw = float(np.clip(raw[2], -1.0, 1.0))
            entry_offset_raw = float(np.clip(raw[3], -1.0, 1.0))
            tp_raw = float(np.clip(raw[4], -1.0, 1.0))
            sl_raw = float(np.clip(raw[5], -1.0, 1.0))

            size = float(np.clip((size_raw + 1.0) * 0.5, 0.0, 1.0))
            target = float(np.clip(direction_raw * size, -1.0, 1.0) * float(max_leverage))
            entry_mode = TradingEnv._entry_mode_from_raw(entry_mode_raw)
            entry_offset_pct = float(entry_offset_raw * 0.005)
            tp_offset_pct = float(0.005 + max(0.0, tp_raw) * 0.015)
            sl_offset_pct = float(0.005 + max(0.0, -sl_raw) * 0.015)

            if abs(direction_raw) < float(min_direction_abs) or size < float(min_size_abs) or abs(target) < float(min_target_abs):
                target = 0.0

            meta = {
                "direction": direction_raw,
                "size": size,
                "target": float(target),
                "entry_mode": entry_mode,
                "entry_offset_pct": entry_offset_pct,
                "tp_offset_pct": tp_offset_pct,
                "sl_offset_pct": sl_offset_pct,
                "legacy": False,
                "action_version": "multi_trade_v1",
            }
            meta["decision_spec"] = DecisionSpec(
                direction=direction_raw,
                lot_spec={"mode": "fixed", "fixed_lots": size},
                entry={"type": entry_mode, "offset_pct": entry_offset_pct},
                tp={"type": "pct", "value": tp_offset_pct},
                sl={"type": "pct", "value": sl_offset_pct},
                legacy=False,
                action_version="multi_trade_v1",
                raw_action=raw.tolist(),
            )
            return meta

        # ============================================================
        # FULL DECISION PPO RICH PATH (n >= 8, recommended 18)
        # ============================================================
        # Raw vector layout (all in [-1,1], mapped intelligently):
        # [0]  direction_raw
        # [1]  lot_mode_raw (risk/fixed/vol)
        # [2]  lot_risk_or_size_raw
        # [3]  tp_type_raw
        # [4]  tp_value_raw
        # [5]  sl_type_raw
        # [6]  sl_value_raw
        # [7]  trail_enable_raw
        # [8]  trail_dist_raw
        # [9]  partial_enable_raw
        # [10] partial_close_pct_raw
        # [11] max_hold_norm
        # [12] be_enable_raw
        # [13] be_trigger_raw
        # [14] entry_type_raw
        # [15] confidence_raw
        # [16] vol_target_raw
        # [17] ... (padding / future: rr_ratio, etc.)

        direction_raw = float(np.clip(raw[0], -1.0, 1.0))
        lot_mode_raw = float(raw[1]) if n > 1 else 0.0
        lot_val_raw = float(raw[2]) if n > 2 else 0.0
        tp_type_raw = float(raw[3]) if n > 3 else 0.0
        tp_val_raw = float(raw[4]) if n > 4 else 0.5
        sl_type_raw = float(raw[5]) if n > 5 else 0.0
        sl_val_raw = float(raw[6]) if n > 6 else -0.5
        trail_en_raw = float(raw[7]) if n > 7 else -0.5
        trail_dist_raw = float(raw[8]) if n > 8 else 0.0
        part_en_raw = float(raw[9]) if n > 9 else -0.5
        part_pct_raw = float(raw[10]) if n > 10 else 0.0
        max_hold_raw = float(raw[11]) if n > 11 else 0.0
        be_en_raw = float(raw[12]) if n > 12 else 0.5
        be_trig_raw = float(raw[13]) if n > 13 else 0.0
        entry_type_raw = float(raw[14]) if n > 14 else -0.8
        conf_raw = float(raw[15]) if n > 15 else 0.0
        vol_target_raw = float(raw[16]) if n > 16 else 0.0

        # Map
        lot_types = ["risk_based", "fixed", "vol_target"]
        lot_mode = _discretize_type(lot_mode_raw, lot_types)

        risk_pct = float(np.clip((lot_val_raw + 1.0) * 0.5 * 0.029 + 0.001, 0.001, 0.03))
        fixed_lots = float(np.clip((lot_val_raw + 1.0) * 0.5 * 0.99 + 0.01, 0.01, 1.0))
        vol_targ = float(np.clip((vol_target_raw + 1.0) * 0.5 * 0.02 + 0.002, 0.002, 0.02))

        lot_spec = {
            "mode": lot_mode,
            "risk_pct_equity": risk_pct if lot_mode == "risk_based" else 0.005,
            "fixed_lots": fixed_lots if lot_mode == "fixed" else 0.01,
            "vol_target_pct": vol_targ if lot_mode == "vol_target" else 0.01,
            "atr_mult_for_size": 1.0,
        }

        tp_types = ["pct", "atr", "price", "rr"]
        tp_type = _discretize_type(tp_type_raw, tp_types)
        tp_val = float(0.003 + max(0.0, tp_val_raw) * 0.025)  # 0.3% - 2.8%
        tp_spec = {"type": tp_type, "value": tp_val, "rr": 2.0, "atr_period": 14}

        sl_types = ["pct", "atr", "price", "rr"]
        sl_type = _discretize_type(sl_type_raw, sl_types)
        sl_val = float(0.002 + max(0.0, -sl_val_raw) * 0.02)
        sl_spec = {"type": sl_type, "value": sl_val, "atr_period": 14, "rr": 1.0}

        trail_enabled = trail_en_raw > 0.0
        trail_dist = float(0.001 + max(0.0, trail_dist_raw) * 0.008)
        trail_spec = {
            "enabled": bool(trail_enabled),
            "type": "pct",
            "distance": trail_dist,
            "step": max(0.0005, trail_dist * 0.5),
            "activation_trigger_pct_or_atr": 0.003,
            "atr_mult": 1.5,
        }

        partial_enabled = part_en_raw > 0.1
        partial_close_pct = float(np.clip((part_pct_raw + 1.0) * 0.5, 0.1, 0.9))
        partial_spec = {
            "enabled": bool(partial_enabled),
            "levels": [
                {"trigger_profit_pct": 0.004, "close_pct": partial_close_pct, "move_sl_to_be": True},
                {"trigger_profit_pct": 0.012, "close_pct": 0.3, "move_sl_to_be": False},
            ],
        }

        max_hold_bars = int(30 + np.clip((max_hold_raw + 1.0) * 0.5, 0.0, 1.0) * 470)  # 30-500 bars
        be_enabled = be_en_raw > -0.2
        be_trigger = float(0.001 + max(0.0, be_trig_raw) * 0.006)
        be_spec = {
            "enabled": bool(be_enabled),
            "trigger_fav_pct": be_trigger,
            "lock_profit_pct": 0.0,
            "type": "pct",
        }

        entry_types = ["market", "limit", "stop"]
        entry_type = _discretize_type(entry_type_raw, entry_types)
        entry_spec = {"type": entry_type, "offset_pct": 0.0}

        confidence = float(np.clip((conf_raw + 1.0) * 0.5, 0.1, 0.99))

        # Size from risk (for env simulation we still use fractional size derived from risk_pct)
        # Direction * effective size will be resolved in simulation using risk engine semantics
        size_approx = float(np.clip(risk_pct * 50.0, 0.05, 0.95))  # heuristic mapping for legacy "size" consumers
        target = float(np.clip(direction_raw * size_approx, -1.0, 1.0) * float(max_leverage))

        if abs(direction_raw) < float(min_direction_abs) or size_approx < float(min_size_abs) or abs(target) < float(min_target_abs):
            target = 0.0
            direction_raw = 0.0

        rich_meta = {
            "direction": float(direction_raw),
            "size": float(np.clip(size_approx, 0.0, 1.0)),
            "target": float(target),
            "entry_mode": entry_type,
            "entry_offset_pct": 0.0,
            "tp_offset_pct": tp_val if tp_type == "pct" else 0.008,  # legacy compat fields (best effort)
            "sl_offset_pct": sl_val if sl_type == "pct" else 0.004,
            "legacy": False,
            "action_version": "decision_ppo_v1",
            "decision_ppo": True,
            # Rich fields
            "lot_spec": lot_spec,
            "tp_spec": tp_spec,
            "sl_spec": sl_spec,
            "trailing_spec": trail_spec,
            "partial_close_spec": partial_spec,
            "full_close_spec": {"max_hold_bars": max_hold_bars},
            "breakeven_spec": be_spec,
            "confidence": confidence,
        }

        # Attach full structured DecisionSpec (the canonical high-level output)
        decision_spec = DecisionSpec(
            direction=direction_raw,
            confidence=confidence,
            lot_spec=lot_spec,
            entry=entry_spec,
            tp=tp_spec,
            sl=sl_spec,
            trailing=trail_spec,
            partial_close=partial_spec,
            full_close={"max_hold_bars": max_hold_bars},
            breakeven=be_spec,
            risk={"max_risk_per_trade_pct": risk_pct},
            legacy=False,
            action_version="decision_ppo_v1",
            raw_action=raw[: min(n, DECISION_ACTION_DIM)].tolist(),
        )
        rich_meta["decision_spec"] = decision_spec
        rich_meta["decision_spec_dict"] = decision_spec.to_dict()  # convenience for JSON handoff

        return rich_meta

    @staticmethod
    def _entry_mode_from_raw(value: float) -> str:
        if value <= -0.33:
            return "market"
        if value <= 0.33:
            return "limit"
        return "stop"

    def _extract_arrays(self, df):
        if isinstance(df, pl.DataFrame):
            pdf = df.to_pandas()
        elif isinstance(df, pd.DataFrame):
            pdf = df.copy()
        else:
            pdf = pl.DataFrame(df).to_pandas()

        pdf.columns = [str(c).lower() for c in pdf.columns]
        if "tick_volume" in pdf.columns and "volume" not in pdf.columns:
            pdf = pdf.rename(columns={"tick_volume": "volume"})

        required = ["open", "high", "low", "close"]
        for c in required:
            if c not in pdf.columns:
                raise ValueError(f"missing required column: {c}")

        if "volume" not in pdf.columns:
            pdf["volume"] = 0.0

        dates = None
        if "time" in pdf.columns:
            dates = pd.to_datetime(pdf["time"], utc=True, errors="coerce")
        elif isinstance(pdf.index, pd.DatetimeIndex):
            dates = pd.to_datetime(pdf.index, utc=True, errors="coerce")

        o = pdf["open"].to_numpy(dtype=np.float64)
        h = pdf["high"].to_numpy(dtype=np.float64)
        l = pdf["low"].to_numpy(dtype=np.float64)
        c = pdf["close"].to_numpy(dtype=np.float64)
        v = pdf["volume"].to_numpy(dtype=np.float64)
        return o, h, l, c, v, dates

    def _build_feature_matrix(self, o, h, l, c, v, dates):
        eps = 1e-12
        range_ = np.maximum(h - l, eps)

        close_shift1 = self._shift(c, 1)
        close_shift5 = self._shift(c, 5)
        close_shift20 = self._shift(c, 20)

        log_ret1 = np.log(np.maximum(c, eps) / np.maximum(close_shift1, eps))
        log_ret5 = np.log(np.maximum(c, eps) / np.maximum(close_shift5, eps))
        log_ret20 = np.log(np.maximum(c, eps) / np.maximum(close_shift20, eps))

        body_ratio = (c - o) / range_
        upper_wick = (h - np.maximum(o, c)) / range_
        lower_wick = (np.minimum(o, c) - l) / range_
        range_ratio = self._safe_div(h - l, c)

        rv_20 = self._rolling_std(log_ret1, 20)
        vol_ma20 = self._rolling_mean(np.maximum(v, 0.0), 20)
        rel_volume = self._safe_div(np.maximum(v, 0.0), vol_ma20)
        spread_est_bps = self._safe_div(h - l, c) * 10000.0

        ma50 = self._rolling_mean(c, 50)
        htf_trend = self._safe_div(c, ma50) - 1.0

        hour_sin = np.zeros_like(c)
        hour_cos = np.zeros_like(c)
        dow_sin = np.zeros_like(c)
        dow_cos = np.zeros_like(c)
        if dates is not None:
            dt = pd.to_datetime(dates, utc=True, errors="coerce")
            if isinstance(dt, pd.DatetimeIndex):
                hour = dt.hour.astype(np.float64)
                dow = dt.dayofweek.astype(np.float64)
            else:
                hour = dt.dt.hour.to_numpy(dtype=np.float64)
                dow = dt.dt.dayofweek.to_numpy(dtype=np.float64)
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

        close_rel = self._safe_div(c, close_shift1) - 1.0
        open_rel = self._safe_div(o, c) - 1.0
        high_rel = self._safe_div(h, c) - 1.0
        low_rel = self._safe_div(l, c) - 1.0
        log_vol = np.log1p(np.maximum(v, 0.0))

        mat = np.column_stack(
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

        mat = np.nan_to_num(mat, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        return mat

    def _set_data(self, df):
        o, h, l, c, v, dates = self._extract_arrays(df)
        self.prices = c.astype(np.float64)
        self.highs = h.astype(np.float64)
        self.lows = l.astype(np.float64)
        self.opens = o.astype(np.float64)
        base = pd.DataFrame(
            {
                "time": dates if dates is not None else pd.RangeIndex(len(c)),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            }
        )
        self.feature_data = build_env_feature_matrix(base, feature_version=self.feature_version)
        self.n_features = int(self.feature_data.shape[1])

        # Precompute ATR for rich TP/SL/trailing in Decision PPO
        self.atr = self._compute_atr_series(self.highs, self.lows, self.prices, period=14)
        self.atr_fast = self._compute_atr_series(self.highs, self.lows, self.prices, period=7)

        self._update_observation_space()
        self.reset()

    def _use_synthetic(self):
        n = 2000
        price = 1.10 + np.cumsum(np.random.randn(n) * 0.001)
        o = price + np.random.randn(n) * 0.0001
        h = np.maximum(o, price) + np.abs(np.random.randn(n) * 0.0004)
        l = np.minimum(o, price) - np.abs(np.random.randn(n) * 0.0004)
        v = np.random.randint(100, 10000, n).astype(float)
        dates = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")

        self.prices = price.astype(np.float64)
        self.highs = h.astype(np.float64)
        self.lows = l.astype(np.float64)
        self.opens = o.astype(np.float64)
        base = pd.DataFrame(
            {
                "time": dates,
                "open": o,
                "high": h,
                "low": l,
                "close": price,
                "volume": v,
            }
        )
        self.feature_data = build_env_feature_matrix(base, feature_version=self.feature_version)
        self.n_features = int(self.feature_data.shape[1])

        self.atr = self._compute_atr_series(self.highs, self.lows, self.prices, period=14)
        self.atr_fast = self._compute_atr_series(self.highs, self.lows, self.prices, period=7)

        self._update_observation_space()
        self.reset()

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = self.window_size
        self.equity = self.initial_balance
        self.position = 0.0
        self.last_action = {"direction": 0.0, "size": 0.0, "target": 0.0, "legacy": False, "decision_ppo": self.decision_ppo}
        self.peak_equity = self.initial_balance
        self.recent_returns = np.zeros(50, dtype=np.float32)
        self.pending_order = None
        self.open_trade = None
        # Decision PPO rich state
        self.steps_held = 0
        self.current_decision_spec: DecisionSpec | None = None
        self.partials_executed: list = []
        return self._get_obs(), {}

    def step(self, action: np.ndarray):
        action_meta = self.decode_action(
            action,
            max_leverage=self.max_leverage,
            min_direction_abs=float(self.action_config.get("min_direction_abs", 0.03)),
            min_size_abs=float(self.action_config.get("min_size_abs", 0.03)),
            min_target_abs=float(self.action_config.get("min_target_abs", 0.03)),
            decision_ppo=bool(self.decision_ppo),
            decision_action_dim=int(self.decision_action_dim),
        )
        prev_equity = self.equity
        prev_position = float(self.position)

        current_price = float(self.prices[self.current_step])
        prev_price = float(self.prices[self.current_step - 1])

        price_ret = (current_price - prev_price) / (prev_price + 1e-12)
        pnl = self.position * prev_equity * price_ret
        self.equity += pnl

        self._process_action(action_meta, current_price)
        self._update_open_trade(current_price)

        delta = self.position - prev_position
        traded_notional = abs(delta) * self.equity
        commission_cost = traded_notional * self.commission_rate
        spread_cost = traded_notional * (self.spread_bps / 10000.0)
        slippage_cost = traded_notional * (self.slippage_bps / 10000.0)  # ALIGNMENT FIX: now modeled (was zero)
        total_cost = commission_cost + spread_cost + slippage_cost

        self.equity -= total_cost
        self.last_action = action_meta

        self.peak_equity = max(self.peak_equity, self.equity)
        self.equity_curve.append(float(self.equity))
        drawdown = (self.peak_equity - self.equity) / (self.peak_equity + 1e-12)

        step_ret = (self.equity - prev_equity) / (prev_equity + 1e-12)
        self.recent_returns = np.roll(self.recent_returns, -1)
        self.recent_returns[-1] = step_ret

        vol = float(np.std(self.recent_returns) + 1e-8)
        sharpe = float(np.mean(self.recent_returns) / (vol + 1e-12))

        payoff = max(step_ret, 0.0) - 0.5 * abs(min(step_ret, 0.0))
        rw = self.reward_weights  # ensure defined before use in DD/cost
        # ALIGNMENT FIX (per TRAINING_OBJECTIVE_ALIGNMENT_AUDIT 1.1): lower threshold + tail emphasis for live DD realism
        dd_excess = max(0.0, drawdown - 0.04)
        dd_tail = max(0.0, drawdown - 0.10) * 5.0
        # FIX (Reward Scale & Signal): removed erroneous double-application of drawdown_penalty weight.
        # Previously: dd_penalty = 8.0 * (excess + ...) then later * another 8.0 → effective ~64x (major source of -1.8k ep_rew).
        # Now: raw excess measure, weight applied once below (preserves hardened 8.0 + tail + 4% thresh intent exactly).
        dd_base = (dd_excess + dd_excess * dd_tail)

        cost_penalty = total_cost / (prev_equity + 1e-12)
        churn_penalty = abs(delta)
        sharpe_bonus = max(0.0, sharpe)
        target_val = float(action_meta.get("target", 0.0) or 0.0)
        target_mag = abs(target_val)
        directional_followthrough = target_val * float(price_ret)
        neutral_epsilon = float(self.action_config.get("neutral_target_epsilon", self.action_config.get("min_target_abs", 0.03)))
        neutral_return_floor = float(self.action_config.get("neutral_return_floor", 0.0006))
        actionable_target_bonus = target_mag if directional_followthrough > 0.0 and target_mag >= neutral_epsilon else 0.0
        neutral_collapse_penalty = 0.0
        if target_mag < neutral_epsilon and abs(float(price_ret)) >= neutral_return_floor:
            neutral_collapse_penalty = float(min(1.0, abs(float(price_ret)) / max(neutral_return_floor, 1e-12)))
        mem_expectancy = float(self.memory_features.get("expectancy_norm", 0.0))
        mem_loss_streak = float(self.memory_features.get("loss_streak_norm", 0.0))
        memory_growth_scale = float(np.clip(1.0 + rw["memory_expectancy_bonus"] * mem_expectancy, 0.5, 1.5))
        growth_term = memory_growth_scale * step_ret
        loss_streak_penalty = rw["loss_streak_penalty"] * mem_loss_streak * churn_penalty

        # Base shaped reward (existing structure preserved for compatibility)
        # REFACTORED for Reward Scale & Signal Improvement: separate bonuses vs penalties so penalty_scale
        # can lighten risk terms (DD/cost/churn) for early training stability while keeping full hardened modeling
        # at default (penalty_scale=1.0). This + env flags + wrapper gives launchers full control for v5/v6 without
        # risking policy collapse to "do nothing" from overwhelming negatives.
        bonus_contrib = (
            rw["growth"] * growth_term
            + rw["payoff"] * payoff
            + rw["sharpe_bonus"] * sharpe_bonus
            + rw["directional_followthrough"] * directional_followthrough
            + rw["actionable_target_bonus"] * actionable_target_bonus
        )
        penalty_contrib = (
            rw["drawdown_penalty"] * dd_base
            + rw["cost_penalty"] * cost_penalty
            + rw["churn_penalty"] * churn_penalty
            + loss_streak_penalty
            + rw["neutral_collapse_penalty"] * neutral_collapse_penalty
        )
        shaped_reward = bonus_contrib - (self.penalty_scale * penalty_contrib)

        # ALIGNMENT: optionally blend/override with the full TradingReward class (includes explicit slippage + risk violation)
        # For this sprint we keep the shaped bonuses but ensure costs + DD now reflect live reality.
        # Future: reward = self.trading_reward.compute(... )["reward"] as primary.
        # Note: TradingReward now also respects the same self.penalty_scale (set at construction).
        try:
            hold_steps = int(getattr(self, "steps_held", 0))
            # Risk used heuristic from open trade or last decision (Decision PPO)
            risk_used = 0.0
            if self.last_action and isinstance(self.last_action.get("decision_spec"), DecisionSpec):
                rs = self.last_action["decision_spec"].risk.get("max_risk_per_trade_pct", 0.01)
                risk_used = float(rs)
            elif self.open_trade:
                risk_used = float(self.open_trade.get("decision_spec", {}).get("risk", {}).get("max_risk_per_trade_pct", 0.01)) if self.open_trade.get("decision_spec") else 0.01

            tr_out = self.trading_reward.compute(
                prev_equity=prev_equity,
                current_equity=self.equity + total_cost,  # pre-cost for raw calc inside class
                prev_position=prev_position,
                current_position=self.position,
                current_price=current_price,
                prev_price=prev_price,
                drawdown=drawdown,
                hold_steps=hold_steps,
                risk_used=risk_used,
                # Pass timing signals so the reward can reward/penalize around market opens and news (user requirement)
                news_proximity=getattr(self, "last_news_proximity", 0.0),
                major_open_window=getattr(self, "last_major_open_window", 0.0),
                news_avoidance_zone=getattr(self, "last_news_avoidance", 0.0),
            )
            # Blend: use class pnl_after_costs term + our shaped bonuses/penalties (conservative rollout)
            reward = 0.6 * tr_out["reward"] + 0.4 * shaped_reward
        except Exception:
            reward = shaped_reward  # fall back to shaped reward on any issue

        # Final scales (global magnitude for stability/logging; applied after blend/clip intent preserved for internal units)
        reward = reward * self.reward_scale
        reward = float(np.clip(reward, -5.0, 5.0))
        self._trade_metrics = {}  # Clear after consuming close bonus

        terminated = bool(drawdown > self.max_drawdown or self.equity <= 0)
        truncated = bool(self.current_step >= len(self.prices) - 1)

        info = {
            "equity": float(self.equity),
            "position": float(self.position),
            "drawdown": float(drawdown),
            "vol": float(vol),
            "sharpe": float(sharpe),
            "cost": float(total_cost),
            "feature_version": self.feature_version,
            "action_version": self.action_version,
            "action_components": {
                "direction": float(action_meta.get("direction", 0.0)),
                "size": float(action_meta.get("size", 0.0)),
                "target": float(action_meta.get("target", 0.0)),
                "entry_mode": action_meta.get("entry_mode", "market"),
                "entry_offset_pct": float(action_meta.get("entry_offset_pct", 0.0)),
                "tp_offset_pct": float(action_meta.get("tp_offset_pct", 0.0)),
                "sl_offset_pct": float(action_meta.get("sl_offset_pct", 0.0)),
                "legacy": bool(action_meta.get("legacy", True)),
                # Decision PPO rich extensions (present when decision_ppo)
                "decision_ppo": bool(action_meta.get("decision_ppo", False)),
                "lot_spec": action_meta.get("lot_spec"),
                "tp_spec": action_meta.get("tp_spec"),
                "sl_spec": action_meta.get("sl_spec"),
                "trailing_spec": action_meta.get("trailing_spec"),
                "confidence": float(action_meta.get("confidence", 0.5)),
            },
            "reward_components": {
                "growth": float(growth_term),
                "payoff": float(payoff),
                "sharpe_bonus": float(sharpe_bonus),
                "directional_followthrough": float(directional_followthrough),
                "actionable_target_bonus": float(actionable_target_bonus),
                "drawdown_penalty": float(dd_base),  # raw excess+tail measure (effective penalty uses weights * penalty_scale)
                "cost_penalty": float(cost_penalty),
                "churn_penalty": float(churn_penalty),
                "loss_streak_penalty": float(loss_streak_penalty),
                "neutral_collapse_penalty": float(neutral_collapse_penalty),
                "memory_expectancy_norm": float(mem_expectancy),
                "weights": rw,
                "scales": {"reward_scale": self.reward_scale, "penalty_scale": self.penalty_scale},  # NEW: diagnostics for v5+
            },
            "trade_state": self._trade_state_snapshot(current_price),
            "profitability": {
                "equity_curve": list(self.equity_curve)[-5:] if self.equity_curve else [],
                "trade_metrics": dict(self._trade_metrics),
            },
        }

        self._log_profit_snapshot(current_price, info)

        self.current_step += 1
        return self._get_obs(), reward, terminated, truncated, info

    def _get_obs(self):
        window = self.feature_data[self.current_step - self.window_size : self.current_step].copy()
        obs_window = window.flatten().astype(np.float32)
        portfolio_state = np.array(self._build_portfolio_state(), dtype=np.float32)
        return np.concatenate([obs_window, portfolio_state]).astype(np.float32)

    def _build_portfolio_state(self) -> list[float]:
        base = [
            self.equity / self.initial_balance,
            self.position,
            float(np.mean(self.recent_returns)),
            float(self.memory_features.get("win_rate_norm", 0.0)),
            float(self.memory_features.get("expectancy_norm", 0.0)),
            float(self.memory_features.get("loss_ratio_norm", 0.0)),
        ]
        if self.portfolio_feature_count <= 0:
            return []
        return base[: min(self.portfolio_feature_count, len(base))]

    def set_portfolio_feature_count(self, count: int):
        self.portfolio_feature_count = max(0, min(self.max_portfolio_features, int(count)))
        self._update_observation_space()

    def _update_observation_space(self):
        shape = self.window_size * self.n_features + self.portfolio_feature_count
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(shape,),
            dtype=np.float32,
        )

    def _trade_state_snapshot(self, current_price: float) -> dict:
        return {
            "open_trade": None if not self.open_trade else dict(self.open_trade),
            "pending_order": None if not self.pending_order else dict(self.pending_order),
            "current_price": float(current_price),
        }

    def _log_profit_snapshot(self, current_price: float, info: dict):
        payload = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "equity": float(self.equity),
            "position": float(self.position),
            "current_price": float(current_price),
            "trade_state": info.get("trade_state"),
            "profitability": info.get("profitability"),
        }
        try:
            _PROFIT_LOG_MAX = 50 * 1024 * 1024  # 50 MB cap
            if os.path.exists(self.profit_log_path) and os.path.getsize(self.profit_log_path) >= _PROFIT_LOG_MAX:
                backup = self.profit_log_path + ".1"
                if os.path.exists(backup):
                    os.remove(backup)
                os.rename(self.profit_log_path, backup)
            with open(self.profit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass

    def _process_action(self, action_meta: dict, current_price: float):
        if self.open_trade and self.open_trade.get("is_open"):
            return

        # Decision PPO: prefer rich decision_spec if present
        dspec = action_meta.get("decision_spec")
        if isinstance(dspec, DecisionSpec):
            self.current_decision_spec = dspec
        elif isinstance(action_meta.get("decision_spec_dict"), dict):
            self.current_decision_spec = DecisionSpec.from_dict(action_meta["decision_spec_dict"])

        direction = float(np.sign(action_meta.get("direction", 0.0)) or 1.0)
        entry_mode = action_meta.get("entry_mode", "market")
        entry_offset = float(action_meta.get("entry_offset_pct", 0.0))
        if entry_mode == "market":
            entry_price = self._compute_entry_price(direction, current_price, entry_offset)
            self._open_trade(action_meta, entry_price)
            return

        entry_price = self._compute_entry_price(direction, current_price, entry_offset)
        self.pending_order = {
            "mode": action_meta.get("entry_mode", "market"),
            "entry_price": float(entry_price),
            "direction": direction,
            "size": float(action_meta.get("size", 0.1)),
            "tp_offset_pct": float(action_meta.get("tp_offset_pct", 0.008)),
            "sl_offset_pct": float(action_meta.get("sl_offset_pct", 0.004)),
            "action_meta": action_meta,
            "decision_spec": self.current_decision_spec,
        }
        self.position = 0.0

    def _update_open_trade(self, current_price: float):
        if self.pending_order and self.pending_order.get("mode"):
            if self._check_pending_fill(current_price):
                entry_price = float(self.pending_order["entry_price"])
                self._open_trade(self.pending_order["action_meta"], entry_price)
                self.pending_order = None

        if self.open_trade and self.open_trade.get("is_open"):
            direction = float(self.open_trade["direction"])
            tp = float(self.open_trade["tp_price"])
            sl = float(self.open_trade["sl_price"])
            hit_tp = (direction > 0 and current_price >= tp) or (direction < 0 and current_price <= tp)
            hit_sl = (direction > 0 and current_price <= sl) or (direction < 0 and current_price >= sl)
            entry_price = float(self.open_trade["entry_price"])

            # Advance hold counter (used for max_hold + reward)
            self.open_trade["steps_held"] = int(self.open_trade.get("steps_held", 0)) + 1
            self.steps_held = int(self.open_trade["steps_held"])

            if direction > 0:
                fav = max(0.0, (current_price - entry_price) / (entry_price + 1e-12))
                adv = max(0.0, (entry_price - current_price) / (entry_price + 1e-12))
            else:
                fav = max(0.0, (entry_price - current_price) / (entry_price + 1e-12))
                adv = max(0.0, (current_price - entry_price) / (entry_price + 1e-12))
            self.open_trade["max_fav"] = max(self.open_trade.get("max_fav", 0.0), fav)
            self.open_trade["max_adv"] = max(self.open_trade.get("max_adv", 0.0), adv)

            # === RICH DECISION PPO: configurable breakeven ===
            be_cfg = self.open_trade.get("breakeven_config") or {}
            be_trig = float(be_cfg.get("trigger_fav_pct", self.breakeven_trigger_pct))
            if not self.open_trade.get("breakeven_triggered") and self.open_trade["max_fav"] >= be_trig:
                self.open_trade["breakeven_triggered"] = True
                lock = float(be_cfg.get("lock_profit_pct", 0.0))
                lock_price = entry_price * (1.0 + lock) if direction > 0 else entry_price * (1.0 - lock)
                self.open_trade["sl_price"] = float(max(sl, min(lock_price, current_price) if direction > 0 else min(lock_price, current_price)))

            # === RICH DECISION PPO: configurable trailing ===
            trail_cfg = self.open_trade.get("trailing_config") or {}
            trail_trig = float(trail_cfg.get("activation_trigger_pct_or_atr", self.trailing_trigger_pct))
            if not self.open_trade.get("trailing_active") and self.open_trade["max_fav"] >= trail_trig:
                self.open_trade["trailing_active"] = True

            if self.open_trade.get("trailing_active") and trail_cfg.get("enabled", False):
                ttype = trail_cfg.get("type", "pct")
                dist = float(trail_cfg.get("distance", self.trailing_distance_pct))
                step = float(trail_cfg.get("step", self.trailing_step_pct))
                atr_entry = float(self.open_trade.get("entry_atr", entry_price * 0.001))

                if ttype == "atr":
                    trail_distance = dist * atr_entry
                else:
                    trail_distance = dist * entry_price

                new_sl = current_price - trail_distance if direction > 0 else current_price + trail_distance
                last_trail = self.open_trade.get("last_trailing_price", entry_price)
                moved = abs(new_sl - float(self.open_trade["sl_price"]))
                if moved >= step:
                    self.open_trade["sl_price"] = float(new_sl)
                    self.open_trade["last_trailing_price"] = float(new_sl)
                    self.open_trade["trailing_moves"] = int(self.open_trade.get("trailing_moves", 0) + 1)

            # === RICH: Partial close logic ===
            partial_cfg = self.open_trade.get("partial_config") or {}
            if partial_cfg.get("enabled") and self.open_trade.get("size", 0.0) > 0.01:
                for lvl in partial_cfg.get("levels", []):
                    trig = float(lvl.get("trigger_profit_pct", 0.005))
                    if self.open_trade["max_fav"] >= trig and not any(p.get("trigger") == trig for p in self.open_trade.get("partials", [])):
                        close_frac = float(lvl.get("close_pct", 0.5))
                        cur_size = float(self.open_trade["size"])
                        reduce = cur_size * close_frac
                        self.open_trade["size"] = max(0.0, cur_size - reduce)
                        self.position = direction * self.open_trade["size"]
                        self.open_trade.setdefault("partials", []).append({
                            "trigger": trig,
                            "close_pct": close_frac,
                            "price": float(current_price),
                            "pnl_contrib": (current_price - entry_price) * reduce * (1 if direction > 0 else -1),
                        })
                        if lvl.get("move_sl_to_be"):
                            self.open_trade["sl_price"] = float(entry_price)
                        self.partials_executed.append({"at_fav": self.open_trade["max_fav"], "closed": close_frac})

            # === RICH: Max hold time exit (Decision PPO full_close) ===
            max_hold = int(self.open_trade.get("max_hold_bars", 300))
            if self.steps_held >= max_hold:
                self._close_trade(current_price, "time_exit")
                return

            if hit_tp:
                self._close_trade(current_price, "tp")
            elif hit_sl:
                self._close_trade(current_price, "sl")

    def _compute_entry_price(self, direction: float, current_price: float, offset_pct: float) -> float:
        if direction >= 0:
            return float(current_price * (1.0 + offset_pct))
        return float(current_price * (1.0 - offset_pct))

    def _open_trade(self, action_meta: dict, entry_price: float):
        direction = float(np.sign(action_meta.get("direction", 0.0)) or 1.0)
        size = float(action_meta.get("size", 0.0))

        # Prefer rich DecisionSpec for TP/SL/trailing/BE/partials/hold
        dspec: DecisionSpec | None = action_meta.get("decision_spec") or self.current_decision_spec
        if not isinstance(dspec, DecisionSpec):
            # Fallback to legacy pct offsets
            tp_pct = float(action_meta.get("tp_offset_pct", 0.008))
            sl_pct = float(action_meta.get("sl_offset_pct", 0.004))
            if direction >= 0:
                tp_price = float(entry_price * (1.0 + tp_pct))
                sl_price = float(entry_price * (1.0 - sl_pct))
            else:
                tp_price = float(entry_price * (1.0 - tp_pct))
                sl_price = float(entry_price * (1.0 + sl_pct))
            trailing_cfg = {"enabled": False, "distance": 0.002}
            be_cfg = {"enabled": True, "trigger_fav_pct": self.breakeven_trigger_pct}
            max_hold = 300
            partial_cfg = {"enabled": False, "levels": []}
        else:
            # === FULL RICH DECISION PPO COMPUTATION ===
            idx = min(self.current_step, len(self.atr) - 1)
            atr_now = float(self.atr[idx]) if hasattr(self, "atr") and len(self.atr) > 0 else entry_price * 0.001

            def _resolve_price_or_dist(spec: dict, base_price: float, atr_val: float, direction_sign: float) -> float:
                t = spec.get("type", "pct")
                val = float(spec.get("value", 0.005))
                if t == "price":
                    return float(val)
                if t == "atr":
                    dist = val * atr_val
                    return base_price + (dist if direction_sign >= 0 else -dist)
                if t == "rr":
                    # RR relative to SL not yet known; approximate using sl value if present
                    slv = float(dspec.sl.get("value", 0.004))
                    rr = float(spec.get("rr", 2.0))
                    base_dist = slv * base_price if dspec.sl.get("type") == "pct" else slv * atr_val
                    return base_price + (base_dist * rr if direction_sign >= 0 else -base_dist * rr)
                # default pct
                return base_price * (1.0 + (val if direction_sign >= 0 else -val))

            # TP
            tp_price = float(_resolve_price_or_dist(dspec.tp, entry_price, atr_now, direction))
            # SL
            sl_price = float(_resolve_price_or_dist(dspec.sl, entry_price, atr_now, -direction))  # opposite side

            # Ensure sensible ordering (never invert)
            if direction > 0:
                tp_price = max(tp_price, entry_price * 1.0005)
                sl_price = min(sl_price, entry_price * 0.9995)
            else:
                tp_price = min(tp_price, entry_price * 0.9995)
                sl_price = max(sl_price, entry_price * 1.0005)

            trailing_cfg = dspec.trailing
            be_cfg = dspec.breakeven
            max_hold = int(dspec.full_close.get("max_hold_bars", 240))
            partial_cfg = dspec.partial_close

        self.open_trade = {
            "direction": direction,
            "size": size,
            "entry_price": float(entry_price),
            "tp_price": float(tp_price),
            "sl_price": float(sl_price),
            "entry_mode": action_meta.get("entry_mode", "market"),
            "is_open": True,
            "max_fav": 0.0,
            "max_adv": 0.0,
            "breakeven_triggered": False,
            "trailing_active": False,
            "trailing_moves": 0,
            "last_entry": float(entry_price),
            # Rich Decision PPO state
            "decision_spec": dspec.to_dict() if dspec else None,
            "trailing_config": trailing_cfg,
            "breakeven_config": be_cfg,
            "max_hold_bars": max_hold,
            "partial_config": partial_cfg,
            "steps_held": 0,
            "entry_atr": float(self.atr[min(self.current_step, len(self.atr)-1)]) if hasattr(self, "atr") and len(self.atr) > idx else entry_price * 0.001,
            "partials": [],
            "realized_partial_pnl": 0.0,
        }
        self.position = direction * size
        self.steps_held = 0
        self.partials_executed = []

    def _close_trade(self, exit_price: float, exit_type: str):
        if not self.open_trade:
            return
        entry_price = float(self.open_trade["entry_price"])
        direction = float(self.open_trade["direction"])
        profit = (exit_price - entry_price) if direction > 0 else (entry_price - exit_price)
        exit_quality_reward = 1.0 if exit_type == "tp" else -1.0
        max_fav = float(self.open_trade.get("max_fav", 0.0))
        base = max(max_fav * entry_price, 1e-4)
        trailing_efficiency = min(1.0, abs(profit) / base) if max_fav > 0 else 0.0
        breakeven_reward = 1.0 if self.open_trade.get("breakeven_triggered") else 0.0
        self._trade_metrics = {
            "exit_type": exit_type,
            "profit": float(profit),
            "exit_quality_reward": exit_quality_reward,
            "trailing_efficiency": float(trailing_efficiency),
            "breakeven_reward": float(breakeven_reward),
            "max_favorable": max_fav,
            "max_adverse": float(self.open_trade.get("max_adv", 0.0)),
            "trailing_moves": int(self.open_trade.get("trailing_moves", 0)),
            "partials": list(self.open_trade.get("partials", [])),
            "realized_partial_pnl": float(self.open_trade.get("realized_partial_pnl", 0.0)),
            "steps_held": int(self.open_trade.get("steps_held", 0)),
            "decision_ppo": bool(self.current_decision_spec is not None),
        }
        # Aggregate any remaining partial P&L into final close
        total_pnl = profit + float(self.open_trade.get("realized_partial_pnl", 0.0))
        self._trade_metrics["total_pnl_incl_partials"] = float(total_pnl)
        self.position = 0.0
        self.open_trade = None
        # keep spec for post-close logging
        self.last_decision_spec = self.current_decision_spec
        self.current_decision_spec = None

    def _check_pending_fill(self, current_price: float) -> bool:
        pending = self.pending_order
        if not pending:
            return False

        direction = float(pending["direction"])
        mode = pending.get("mode", "limit")
        entry_price = float(pending["entry_price"])

        if mode == "limit":
            return (direction > 0 and current_price <= entry_price) or (direction < 0 and current_price >= entry_price)
        if mode == "stop":
            return (direction > 0 and current_price >= entry_price) or (direction < 0 and current_price <= entry_price)
        return True

    # ============================================================
    # MTF + Decision PPO compatibility (new standard pipeline)
    # ============================================================
    def set_mtf_data(self, mtf_dfs: dict, symbol: str):
        """Accept pre-aligned 1m+5m+15m+1h dfs for rich multi-timeframe Decision PPO obs."""
        self.mtf_dfs = mtf_dfs
        self.symbol = symbol or self.symbol
        if _HAS_MTF_BUILDER and mtf_dfs:
            try:
                feat_df = build_multitimeframe_features(
                    mtf_dfs.get("1m") or mtf_dfs.get("1min"),
                    mtf_dfs.get("5m") or mtf_dfs.get("5min"),
                    mtf_dfs.get("15m") or mtf_dfs.get("15min"),
                    mtf_dfs.get("1h") or mtf_dfs.get("60min") or mtf_dfs.get("h1"),
                    symbol=self.symbol,
                )
                self.feature_data = feat_df.to_numpy(dtype=np.float32)
                self.n_features = self.feature_data.shape[1]
                self._update_observation_space()
                self.reset()
            except Exception as e:
                # fall back silently (non-breaking)
                pass

    def get_current_decision_spec(self) -> DecisionSpec | None:
        """Return the last rich DecisionSpec (for brain/executor handoff)."""
        return self.current_decision_spec or getattr(self, "last_decision_spec", None)

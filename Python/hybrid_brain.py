"""
Hybrid Brain — PPO + LSTM joint inference engine.

Decision flow:
  1. LSTM (SmartAGI) classifies volatility regime → LOW / MED / HIGH
  2. PPO determines position sizing and direction → continuous action in [-1, 1]
  3. Deadzone logic: if LSTM says LOW_VOLATILITY and confidence > threshold → HOLD
  4. PPO bias correction: subtract per-symbol running mean to center actions around zero
  5. Volatility-scaled exposure: multiply by regime-dependent risk scalar
  6. Canary scaling: reduce position size when running a canary model
  7. Final signal passed to executor for trade reconciliation
"""
import json
import os
import sys
from collections import deque
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from Python.feature_pipeline import build_env_feature_matrix, ENGINEERED_V2


class HybridBrain:
    """
    RL Executor — PPO-first policy with LSTM volatility gating,
    deadzones, and Canary risk scaling.
    """

    def __init__(self, risk, executor, confidence_threshold: float = None):
        self.risk = risk
        self.executor = executor
        # Allow env override: set AGI_DEADZONE_CONFIDENCE=0.99 to effectively disable deadzone
        if confidence_threshold is not None:
            self.confidence_threshold = confidence_threshold
        else:
            self.confidence_threshold = float(os.environ.get("AGI_DEADZONE_CONFIDENCE", "0.85"))

        # Canary lot multiplier (reduce risk for unproven models)
        self.canary_lot_mult = float(os.environ.get("CANARY_LOT_MULT", "0.25"))

        # Per-symbol PPO bias correction
        # Track running mean of PPO outputs per symbol so we can center them
        # If a model consistently outputs +0.005, we subtract 0.005 to get the
        # true directional signal (positive = buy, negative = sell)
        self._ppo_bias_window = int(os.environ.get("AGI_BIAS_WINDOW", "50"))
        self._ppo_bias: dict[str, deque] = {}  # symbol → deque of recent raw PPO outputs

        # Decision ring buffer (last 100 decisions)
        self._decision_history: deque = deque(maxlen=100)

        # Decision JSONL log
        _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._decision_log_path = os.path.join(_base, "logs", "decisions.jsonl")
        os.makedirs(os.path.dirname(self._decision_log_path), exist_ok=True)

        # Device
        try:
            if torch.cuda.is_available():
                self.device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        except Exception:
            self.device = "cpu"

        # Load models from registry
        self.ppo_model = None
        self.vec_env = None
        self.lstm_brain = None
        self._is_canary = False

        self._load_ppo_from_registry()
        self._load_lstm()

        # Track which model slot is active for decision trace
        if self._is_canary:
            self._model_version = "canary"
        elif self.ppo_model is not None:
            self._model_version = "champion"
        else:
            self._model_version = "fallback"

        logger.success(f"HybridBrain initialized on {self.device.upper()} | canary={self._is_canary}")

    def _load_ppo_from_registry(self):
        """Load PPO model + VecNormalize from the model registry (champion or canary)."""
        try:
            from Python.model_registry import ModelRegistry
            registry = ModelRegistry()
            active_dir = registry.load_active_model(prefer_canary=True)

            if active_dir:
                model_path = os.path.join(active_dir, "ppo_trading.zip")
                vec_path = os.path.join(active_dir, "vec_normalize.pkl")

                # Check if this is a canary
                active = registry._read_active()
                self._is_canary = (active.get("canary") is not None and
                                   active_dir == active.get("canary"))

                if os.path.exists(model_path):
                    self.ppo_model = PPO.load(model_path, device=self.device)
                    logger.success(f"PPO loaded from registry: {active_dir}")

                    if os.path.exists(vec_path):
                        # Build a dummy env matching the trained model's obs/action spaces
                        from drl.trading_env import TradingEnv
                        dummy = DummyVecEnv([lambda: TradingEnv(feature_version=ENGINEERED_V2)])
                        self.vec_env = VecNormalize.load(vec_path, dummy)
                        self.vec_env.training = False
                        self.vec_env.norm_reward = False
                        logger.success("VecNormalize loaded from registry")
                else:
                    logger.warning(f"No ppo_trading.zip in {active_dir}")

        except Exception as e:
            logger.warning(f"Failed to load PPO from registry: {e}")

        # Fallback to base model directory
        if self.ppo_model is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base, "models", "ppo_trading.zip")
            vec_path = os.path.join(base, "models", "vec_normalize.pkl")

            if os.path.exists(model_path):
                try:
                    self.ppo_model = PPO.load(model_path, device=self.device)
                    logger.success(f"PPO loaded from fallback: {model_path}")

                    if os.path.exists(vec_path):
                        from drl.trading_env import TradingEnv
                        dummy = DummyVecEnv([lambda: TradingEnv(feature_version=ENGINEERED_V2)])
                        self.vec_env = VecNormalize.load(vec_path, dummy)
                        self.vec_env.training = False
                        self.vec_env.norm_reward = False
                except Exception as e:
                    logger.error(f"Failed to load fallback PPO: {e}")
            else:
                logger.warning("No PPO model found anywhere — brain will use LSTM-only mode")

    def _load_lstm(self):
        """Load the LSTM SmartAGI brain for volatility classification."""
        try:
            from Python.agi_brain import SmartAGI
            self.lstm_brain = SmartAGI()
            logger.success("LSTM SmartAGI brain loaded for volatility gating")
        except Exception as e:
            logger.warning(f"Could not load LSTM brain: {e}")
            self.lstm_brain = None

    def decide(self, symbol: str, df: pd.DataFrame) -> dict:
        """
        Full hybrid inference pipeline.

        Args:
            symbol: Trading symbol (e.g. "EURUSD")
            df: DataFrame with columns [open, high, low, close, volume]

        Returns:
            dict with full decision trace including model info, PPO/LSTM
            details, risk/scaling state, and final action.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        result = {
            "action": "HOLD",
            "exposure": 0.0,
            "symbol": symbol,
            "timestamp": timestamp,

            # Model info
            "model_version": self._model_version,
            "is_canary": self._is_canary,

            # PPO details (populated in step 3)
            "ppo_raw_action": [],
            "ppo_primary_action": 0.0,

            # PPO bias correction (populated in step 4)
            "ppo_bias": 0.0,
            "ppo_corrected_action": 0.0,

            # LSTM details (populated in step 1)
            "lstm_regime": "UNKNOWN",
            "lstm_confidence": 0.0,
            "lstm_top_indicators": [],
            "lstm_top_feature_groups": [],

            # Risk/scaling (populated in steps 5-6)
            "vol_scale": 1.0,
            "canary_scale": 1.0,
            "pre_threshold_exposure": 0.0,

            # Risk engine state
            "risk_can_trade": self.risk.can_trade(),
            "risk_daily_trades": self.risk.daily_trades,
            "risk_dd_pct": round(self.risk.current_dd, 4),

            # Final
            "confidence": 0.0,
            "volatility": "UNKNOWN",
            "reason": "no_signal",
        }

        # ── Step 1: LSTM Volatility Classification ──
        lstm_signal = None
        lstm_confidence = 0.0

        if self.lstm_brain is not None and len(df) >= 60:
            try:
                df_with_sym = df.copy()
                if "symbol" not in df_with_sym.columns:
                    df_with_sym["symbol"] = symbol
                lstm_result = self.lstm_brain.predict(df_with_sym, production=True)
                lstm_signal = lstm_result.get("signal", "LOW_VOLATILITY")
                lstm_confidence = lstm_result.get("confidence", 0.0)

                result["lstm_regime"] = lstm_signal
                result["lstm_confidence"] = round(float(lstm_confidence), 4)
                result["lstm_top_indicators"] = lstm_result.get("top_indicators", [])
                result["lstm_top_feature_groups"] = lstm_result.get("top_feature_groups", [])
                result["volatility"] = lstm_signal
                result["confidence"] = lstm_confidence
            except Exception as e:
                logger.warning(f"LSTM prediction failed: {e}")

        # ── Step 2: Deadzone Gate ──
        # If LSTM says LOW_VOLATILITY with high confidence, don't trade
        if lstm_signal == "LOW_VOLATILITY" and lstm_confidence > self.confidence_threshold:
            result["action"] = "HOLD"
            result["reason"] = f"deadzone (low_vol conf={lstm_confidence:.2%})"
            logger.debug(f"{symbol}: DEADZONE — low volatility, holding")
            self._record_decision(result)
            return result

        # ── Step 3: PPO Position Sizing ──
        ppo_action = 0.0
        ppo_raw_action = []
        if self.ppo_model is not None and len(df) >= 100:
            try:
                obs = self._build_observation(df)
                if obs is not None:
                    # Apply VecNormalize if available
                    if self.vec_env is not None:
                        obs = self.vec_env.normalize_obs(obs)

                    action, _ = self.ppo_model.predict(obs, deterministic=True)
                    # 1D action: direction/exposure in [-1, 1]
                    # Negative = short, positive = long, magnitude = position size
                    ppo_raw_action = [round(float(a), 6) for a in action.flatten()]
                    ppo_action = float(action.flatten()[0])
            except Exception as e:
                logger.warning(f"PPO prediction failed: {e}")

        result["ppo_raw_action"] = ppo_raw_action
        result["ppo_primary_action"] = round(float(ppo_action), 6)

        # ── Step 4: PPO Bias Correction ──
        # Models can develop a systematic directional bias (e.g. always outputting +0.005).
        # We subtract the per-symbol running mean so the signal is centered around zero,
        # allowing both BUY and SELL signals to emerge from the residual.
        ppo_bias = self._update_ppo_bias(symbol, ppo_action)
        ppo_corrected = ppo_action - ppo_bias
        result["ppo_bias"] = round(float(ppo_bias), 6)
        result["ppo_corrected_action"] = round(float(ppo_corrected), 6)

        if abs(ppo_bias) > 0.001:
            logger.info(
                f"{symbol}: PPO bias correction | raw={ppo_action:.6f} "
                f"bias={ppo_bias:.6f} corrected={ppo_corrected:.6f}"
            )

        # Use bias-corrected action for all downstream steps
        ppo_action = ppo_corrected

        # ── Step 5: Volatility-Scaled Exposure ──
        # Scale PPO action by volatility regime
        # Higher volatility → smaller position (risk-adjusted sizing)
        # Lower volatility → larger position (tighter stops allow bigger size)
        from Python.agi_brain import _regime_to_risk_scalar
        vol_scale = _regime_to_risk_scalar(lstm_signal)
        # _regime_to_risk_scalar: HIGH=0.55, MED=0.80, LOW=0.95, unknown=0.75

        result["vol_scale"] = vol_scale
        exposure = ppo_action * vol_scale

        # ── Step 6: Canary Risk Scaling ──
        canary_scale = 1.0
        if self._is_canary:
            canary_scale = self.canary_lot_mult
            exposure *= canary_scale
            result["reason"] = f"canary_scaled (x{self.canary_lot_mult})"

        result["canary_scale"] = canary_scale
        result["pre_threshold_exposure"] = round(float(exposure), 6)

        # ── Step 7: Determine Action ──
        # Sub-threshold: if exposure is too small, treat as HOLD
        action_threshold = float(os.environ.get("AGI_ACTION_THRESHOLD", "0.02"))
        if abs(exposure) < action_threshold:
            result["action"] = "HOLD"
            result["exposure"] = 0.0
            result["reason"] = "sub_threshold"
        elif exposure > 0:
            result["action"] = "BUY"
            result["exposure"] = round(float(exposure), 4)
            result["reason"] = f"ppo_corrected={ppo_action:.4f} bias={ppo_bias:.4f} vol={lstm_signal} scale={vol_scale}"
        else:
            result["action"] = "SELL"
            result["exposure"] = round(float(exposure), 4)
            result["reason"] = f"ppo_corrected={ppo_action:.4f} bias={ppo_bias:.4f} vol={lstm_signal} scale={vol_scale}"

        logger.info(
            f"[HybridBrain] {symbol}: {result['action']} | "
            f"exposure={result['exposure']:.4f} | vol={lstm_signal} | "
            f"conf={lstm_confidence:.2%} | bias={ppo_bias:.4f} | canary={self._is_canary}"
        )

        self._record_decision(result)
        return result

    # ── PPO Bias Correction ─────────────────────────────────────────

    def _update_ppo_bias(self, symbol: str, ppo_action: float) -> float:
        """
        Track and return the per-symbol running mean of PPO outputs.

        When a model consistently outputs positive values (e.g., always ~+0.005),
        we subtract the running mean so the residual reveals the true directional
        signal. This allows both BUY and SELL signals to emerge.

        Returns:
            The current bias (running mean) for this symbol.
        """
        if symbol not in self._ppo_bias:
            self._ppo_bias[symbol] = deque(maxlen=self._ppo_bias_window)

        self._ppo_bias[symbol].append(ppo_action)

        if len(self._ppo_bias[symbol]) >= 3:
            # Use exponential moving average for smoother bias estimation
            samples = list(self._ppo_bias[symbol])
            alpha = 2.0 / (len(samples) + 1)
            ema = samples[0]
            for s in samples[1:]:
                ema = alpha * s + (1 - alpha) * ema
            return ema
        else:
            # Not enough samples yet — return 0 (no correction)
            return 0.0

    def get_ppo_biases(self) -> dict:
        """Return current per-symbol PPO bias values for diagnostics."""
        biases = {}
        for symbol, samples in self._ppo_bias.items():
            if len(samples) >= 3:
                biases[symbol] = {
                    "mean": round(float(np.mean(samples)), 6),
                    "std": round(float(np.std(samples)), 6),
                    "n": len(samples),
                }
            else:
                biases[symbol] = {"mean": 0.0, "std": 0.0, "n": len(samples)}
        return biases

    # ── Decision history & logging helpers ──────────────────────────

    def _record_decision(self, decision: dict):
        """Append decision to ring buffer, JSONL log, and API cache."""
        self._decision_history.append(decision)

        try:
            with open(self._decision_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(decision, default=str) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write decision log: {e}")

        # Feed into the API server decision cache for dashboard access
        try:
            from Python.api_server import cache_decision
            symbol = decision.get("symbol", "UNKNOWN")
            cache_decision(symbol, decision)
        except Exception:
            pass  # API server may not be running

    @property
    def decision_history(self) -> list[dict]:
        """Return a copy of the recent decision ring buffer."""
        return list(self._decision_history)

    def _build_observation(self, df: pd.DataFrame) -> np.ndarray | None:
        """
        Build the observation vector matching TradingEnv engineered_v2 format:
        [window_size * 21 features] + [3 portfolio state features] = (2103,)
        """
        try:
            window_size = 100

            for c in ["open", "high", "low", "close", "volume"]:
                if c not in df.columns:
                    logger.error(f"Missing column '{c}' in data for observation")
                    return None

            # Ensure the DataFrame has a DatetimeIndex or 'time' column
            # so _normalize_ohlcv can produce time-based features.
            feed_df = df.copy()
            if "time" not in feed_df.columns and not isinstance(feed_df.index, pd.DatetimeIndex):
                # Synthesize a DatetimeIndex so time-based features are non-zero
                feed_df.index = pd.date_range(
                    end=pd.Timestamp.utcnow(), periods=len(feed_df), freq="5min", tz="UTC"
                )

            # Build the feature matrix via the feature pipeline (engineered_v2: 21 features)
            feature_matrix = build_env_feature_matrix(feed_df, feature_version=ENGINEERED_V2)

            if len(feature_matrix) < window_size:
                logger.warning(f"Not enough data for observation: {len(feature_matrix)} < {window_size}")
                return None

            window = feature_matrix[-window_size:]
            obs_window = window.flatten()

            # Portfolio state: [equity_ratio, position, avg_return]
            # In live mode we use neutral defaults
            portfolio_state = np.array([1.0, 0.0, 0.0], dtype=np.float32)

            obs = np.concatenate([obs_window, portfolio_state]).astype(np.float32)
            return obs

        except Exception as e:
            logger.error(f"Failed to build observation: {e}")
            return None

    def live_trade(self, symbol: str, df: pd.DataFrame, max_lots: float = None,
                   risk_supervisor=None, max_positions_per_symbol: int = 5):
        """
        Full live trading loop: decide → execute.
        Each cycle can open a new position (up to max_positions_per_symbol).
        """
        if not self.risk.can_trade():
            logger.debug(f"{symbol}: Risk engine blocked trading")
            return

        # RiskSupervisor circuit breaker check
        if risk_supervisor is not None:
            decision_rs = risk_supervisor.can_trade(symbol)
            if not decision_rs.allowed:
                logger.warning(f"{symbol}: RiskSupervisor blocked trading — {decision_rs.reason}")
                return

        if max_lots is None:
            max_lots = self.risk.max_lots

        decision = self.decide(symbol, df)

        if decision["action"] == "HOLD":
            return decision

        # Execute via MT5 or dry-run executor
        try:
            self.executor.reconcile_exposure(
                symbol, decision["exposure"], max_lots,
                max_positions_per_symbol=max_positions_per_symbol
            )
            if risk_supervisor is not None:
                risk_supervisor.mark_trade(symbol)
        except Exception as e:
            logger.error(f"Execution error for {symbol}: {e}")
            self.risk.record_error()

        return decision

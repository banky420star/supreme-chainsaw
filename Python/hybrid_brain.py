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
import glob as _glob
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
            self.confidence_threshold = float(os.environ.get("AGI_DEADZONE_CONFIDENCE", "0.99"))

        # Canary lot multiplier (full sizing for canary models)
        self.canary_lot_mult = float(os.environ.get("CANARY_LOT_MULT", "1.0"))

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

        # Decision log rotation thresholds
        self._decision_log_max_bytes = int(os.environ.get("AGI_DECISION_LOG_MAX_MB", "10")) * 1024 * 1024
        self._decision_log_max_lines = int(os.environ.get("AGI_DECISION_LOG_MAX_LINES", "100000"))
        self._decision_log_max_archives = int(os.environ.get("AGI_DECISION_LOG_MAX_ARCHIVES", "2"))

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

        # Per-symbol PPO model cache: symbol -> {"ppo": PPO, "vec_env": VecNormalize, "is_canary": bool}
        self._per_symbol_ppo: dict[str, dict] = {}

        self._model_version = "fallback"
        self._load_ppo_from_registry()
        self._load_lstm()

        # _model_version is set inside _load_ppo_from_registry() from the
        # actual model directory name (e.g. ppo_20260412_115739).
        # Only fall back to generic labels if loading didn't set one.
        if not hasattr(self, '_model_version') or not self._model_version or self._model_version == "fallback":
            if self._is_canary:
                self._model_version = "canary"
            elif self.ppo_model is not None:
                self._model_version = "champion"

        logger.success(f"HybridBrain initialized on {self.device.upper()} | canary={self._is_canary}")

    def _load_ppo_for_symbol(self, symbol: str) -> dict | None:
        """
        Load a per-symbol PPO model + VecNormalize from the registry.
        Returns dict with "ppo", "vec_env", "is_canary", "model_dir" keys,
        or None if no model is available for that symbol.
        """
        try:
            from Python.model_registry import ModelRegistry
            registry = ModelRegistry()
            active_dir = registry.get_active_model(symbol=symbol, prefer_canary=True)

            if not active_dir:
                return None

            model_path = os.path.join(active_dir, "ppo_trading.zip")
            vec_path = os.path.join(active_dir, "vec_normalize.pkl")

            if not os.path.exists(model_path):
                logger.warning(f"No ppo_trading.zip in per-symbol dir {active_dir}")
                return None

            ppo = PPO.load(model_path, device=self.device)
            vec_env = None
            if os.path.exists(vec_path):
                from drl.trading_env import TradingEnv
                dummy = DummyVecEnv([lambda: TradingEnv(feature_version=ENGINEERED_V2)])
                vec_env = VecNormalize.load(vec_path, dummy)
                vec_env.training = False
                vec_env.norm_reward = False

            is_canary = registry.is_per_symbol_canary(symbol, active_dir)
            if not is_canary:
                active = registry._read_active()
                is_canary = (active.get("canary") is not None and
                             active_dir == active.get("canary"))

            logger.success(f"Per-symbol PPO loaded for {symbol}: {active_dir} (canary={is_canary})")
            return {
                "ppo": ppo,
                "vec_env": vec_env,
                "is_canary": is_canary,
                "model_dir": active_dir,
            }

        except Exception as e:
            logger.warning(f"Failed to load per-symbol PPO for {symbol}: {e}")
            return None

    def _get_ppo_for_symbol(self, symbol: str) -> tuple:
        """
        Get the PPO model, VecNormalize, and canary status for a given symbol.
        Tries per-symbol champion/canary first, falls back to global.

        Returns:
            (ppo_model, vec_env, is_canary, model_version_str)
        """
        # Check per-symbol cache first
        if symbol in self._per_symbol_ppo:
            cached = self._per_symbol_ppo[symbol]
            model_type = "per_symbol_canary" if cached.get("is_canary") else "per_symbol_champion"
            logger.debug(f"[{symbol}] PPO resolved from cache: {cached.get('model_dir', 'unknown')} (type={model_type})")
            return (
                cached["ppo"],
                cached.get("vec_env"),
                cached.get("is_canary", False),
                model_type,
            )

        # Try loading per-symbol model
        per_symbol = self._load_ppo_for_symbol(symbol)
        if per_symbol is not None:
            # Only cache if this is actually a per-symbol model (different from global)
            from Python.model_registry import ModelRegistry
            registry = ModelRegistry()
            global_model = registry.get_active_model(symbol=None, prefer_canary=True)
            if per_symbol["model_dir"] != global_model:
                self._per_symbol_ppo[symbol] = per_symbol
                model_type = "per_symbol_canary" if per_symbol["is_canary"] else "per_symbol_champion"
                logger.info(f"[{symbol}] PPO resolved: {per_symbol['model_dir']} (type={model_type})")
                return (
                    per_symbol["ppo"],
                    per_symbol.get("vec_env"),
                    per_symbol["is_canary"],
                    model_type,
                )

        # Fall back to global model
        model_type = "global_canary" if self._is_canary else "global_champion"
        logger.info(f"[{symbol}] PPO resolved: global fallback (type={model_type}, version={self._model_version})")
        return (
            self.ppo_model,
            self.vec_env,
            self._is_canary,
            self._model_version,
        )

    def _load_ppo_from_registry(self, symbol: str = None):
        """
        Load PPO model + VecNormalize from the model registry (champion or canary).
        If symbol is provided, tries per-symbol champion/canary first, then global.
        """
        try:
            from Python.model_registry import ModelRegistry
            registry = ModelRegistry()
            active_dir = registry.get_active_model(symbol=symbol, prefer_canary=True)

            if active_dir:
                model_path = os.path.join(active_dir, "ppo_trading.zip")
                vec_path = os.path.join(active_dir, "vec_normalize.pkl")

                # Extract model version from directory name (e.g. ppo_20260412_115739)
                model_dir_name = os.path.basename(active_dir.rstrip("/\\"))
                self._model_version = model_dir_name

                # Check if this is a canary (per-symbol or global)
                if symbol:
                    self._is_canary = registry.is_per_symbol_canary(symbol, active_dir)
                if not self._is_canary:
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
        # If LSTM says LOW_VOLATILITY with high confidence, apply conservative filter
        # rather than complete block — allow strong signals through but with reduced size
        if lstm_signal == "LOW_VOLATILITY" and lstm_confidence > self.confidence_threshold:
            # Very high confidence LOW_VOL = flat market, still hold
            if lstm_confidence > 0.98:
                result["action"] = "HOLD"
                result["reason"] = f"deadzone (low_vol conf={lstm_confidence:.2%})"
                logger.debug(f"{symbol}: DEADZONE — low volatility, holding")
                self._record_decision(result)
                return result
            # Moderate LOW_VOL confidence — allow but tag for conservative sizing
            result["regime_note"] = "low_vol_scalp"
            logger.debug(f"{symbol}: LOW_VOL scalp mode — reduced sizing")

        # ── Step 3: PPO Position Sizing ──
        ppo_action = 0.0
        ppo_raw_action = []
        ppo_model, ppo_vec_env, ppo_is_canary, ppo_model_version = self._get_ppo_for_symbol(symbol)
        if ppo_model is not None and len(df) >= 100:
            try:
                obs = self._build_observation(df)
                if obs is not None:
                    # Apply VecNormalize if available
                    if ppo_vec_env is not None:
                        obs = ppo_vec_env.normalize_obs(obs)

                    action, _ = ppo_model.predict(obs, deterministic=True)
                    # 1D action: direction/exposure in [-1, 1]
                    # Negative = short, positive = long, magnitude = position size
                    ppo_raw_action = [round(float(a), 6) for a in action.flatten()]
                    ppo_action = float(action.flatten()[0])
            except Exception as e:
                logger.warning(f"PPO prediction failed: {e}")

        # Update result with per-symbol model info
        result["model_version"] = ppo_model_version
        result["is_canary"] = ppo_is_canary

        result["ppo_raw_action"] = ppo_raw_action
        result["ppo_primary_action"] = round(float(ppo_action), 6)

        # ── Step 4: PPO Bias Correction ──
        # Models can develop a systematic directional bias (e.g. always outputting +0.005).
        # We subtract the per-symbol running mean so the signal is centered around zero,
        # allowing both BUY and SELL signals to emerge from the residual.
        # IMPORTANT: The correction strength is controlled by AGI_BIAS_STRENGTH:
        #   0.0 = no correction (raw signal passes through)
        #   0.5 = cap bias at 50% of raw signal (moderate centering)
        #   1.0 = full correction (subtract entire EMA bias)
        # For aggressive trading, use 0.0 or low values to preserve signal strength.
        ppo_bias = self._update_ppo_bias(symbol, ppo_action)
        bias_strength = float(os.environ.get("AGI_BIAS_STRENGTH", "0.0"))
        # Apply bias strength: 0 = no correction, 1 = full correction
        max_bias = abs(ppo_action) * bias_strength
        ppo_bias_applied = max(-max_bias, min(ppo_bias, max_bias)) if abs(ppo_action) > 0.0001 else ppo_bias * bias_strength
        ppo_corrected = ppo_action - ppo_bias_applied
        result["ppo_bias"] = round(float(ppo_bias_applied), 6)
        result["ppo_bias_raw"] = round(float(ppo_bias), 6)
        result["ppo_corrected_action"] = round(float(ppo_corrected), 6)

        if abs(ppo_bias) > 0.001:
            logger.info(
                f"{symbol}: PPO bias correction | raw={ppo_action:.6f} "
                f"bias_raw={ppo_bias:.6f} bias_applied={ppo_bias_applied:.6f} corrected={ppo_corrected:.6f} "
                f"strength={bias_strength}"
            )

        # Use bias-corrected action for all downstream steps
        ppo_action = ppo_corrected

        # ── Step 5: Volatility-Scaled Exposure (Per-Regime Strategy) ──
        # Each regime has a distinct trading strategy:
        #   LOW_VOL:  Conservative scalping — tight entries, small size, quick exits
        #   MED_VOL:  Standard trend-following — normal sizing, standard thresholds
        #   HIGH_VOL: Breakout/momentum — wide stops, strong conviction required
        from Python.agi_brain import _regime_to_risk_scalar
        vol_scale = _regime_to_risk_scalar(lstm_signal)
        # _regime_to_risk_scalar: HIGH=0.55, MED=0.80, LOW=0.95, unknown=0.75

        # Per-regime action thresholds (minimum PPO conviction to enter)
        _regime_thresholds = {
            "LOW_VOLATILITY": float(os.environ.get("AGI_LOW_VOL_MIN_ACTION", "0.001")),    # Low vol: small signal ok
            "MED_VOLATILITY": float(os.environ.get("AGI_MED_VOL_MIN_ACTION", "0.001")),    # Med vol: small signal ok
            "HIGH_VOLATILITY": float(os.environ.get("AGI_HIGH_VOL_MIN_ACTION", "0.002")),  # High vol: still need conviction
        }
        regime_min_action = _regime_thresholds.get(lstm_signal, 0.005)

        # Per-regime trailing strategies (set as metadata for executor)
        _regime_trailing = {
            "LOW_VOLATILITY": {"trigger": 1.0, "distance": 1.0},  # Tight trail, quick exit
            "MED_VOLATILITY": {"trigger": 1.5, "distance": 1.5},  # Standard trail
            "HIGH_VOLATILITY": {"trigger": 2.0, "distance": 2.5},  # Wide trail, let it run
        }
        result["regime_trailing"] = _regime_trailing.get(lstm_signal, _regime_trailing["MED_VOLATILITY"])

        result["vol_scale"] = vol_scale
        exposure = ppo_action * vol_scale

        # ── Step 5b: Per-Regime Confidence Gate ──
        # Each regime requires minimum PPO conviction scaled to its risk profile
        if abs(ppo_action) < regime_min_action:
            result["action"] = "HOLD"
            result["exposure"] = 0.0
            gate_name = "high_vol_gate" if lstm_signal == "HIGH_VOLATILITY" else "low_vol_gate" if lstm_signal == "LOW_VOLATILITY" else "med_vol_gate"
            result["reason"] = f"{gate_name} (ppo={ppo_action:.4f} < {regime_min_action})"
            logger.info(
                f"[HybridBrain] {symbol}: HOLD ({gate_name}) | "
                f"regime={lstm_signal} ppo={ppo_action:.4f} < {regime_min_action}"
            )
            self._record_decision(result)
            return result

        # ── Step 6: Canary Risk Scaling ──
        canary_scale = 1.0
        if ppo_is_canary:
            canary_scale = self.canary_lot_mult
            exposure *= canary_scale
            result["reason"] = f"canary_scaled (x{self.canary_lot_mult})"

        result["canary_scale"] = canary_scale
        result["pre_threshold_exposure"] = round(float(exposure), 6)

        # ── Step 7: Determine Action ──
        # Sub-threshold: if exposure is too small, treat as HOLD
        action_threshold = float(os.environ.get("AGI_ACTION_THRESHOLD", "0.001"))
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
            f"conf={lstm_confidence:.2%} | bias={ppo_bias:.4f} | canary={ppo_is_canary} | model={ppo_model_version}"
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

    def _rotate_decision_log(self):
        """Check decision log size and rotate if it exceeds thresholds.

        Rotation renames the current log to ``decisions_archive_{timestamp}.jsonl``
        and starts a fresh file. At most ``_decision_log_max_archives`` archive
        files are kept — the oldest is deleted when the limit is exceeded.

        Both byte-size (default 10 MB) and line-count (default 100 000) thresholds
        are checked; rotation triggers when *either* is exceeded.
        """
        log_path = self._decision_log_path
        if not os.path.exists(log_path):
            return

        try:
            file_size = os.path.getsize(log_path)
        except OSError:
            return

        # Fast path: if under byte threshold skip line counting
        needs_rotation = file_size >= self._decision_log_max_bytes

        if not needs_rotation:
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    line_count = sum(1 for _ in f)
                if line_count >= self._decision_log_max_lines:
                    needs_rotation = True
            except Exception:
                return

        if not needs_rotation:
            return

        # Rotate: rename current log to archive
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_dir = os.path.dirname(log_path)
        archive_path = os.path.join(log_dir, f"decisions_archive_{ts}.jsonl")

        try:
            os.rename(log_path, archive_path)
            logger.info(f"Decision log rotated to {archive_path}")
        except OSError as e:
            logger.warning(f"Failed to rotate decision log: {e}")
            return

        # Prune old archives, keeping at most _decision_log_max_archives
        try:
            archive_pattern = os.path.join(log_dir, "decisions_archive_*.jsonl")
            archives = sorted(_glob.glob(archive_pattern))
            while len(archives) > self._decision_log_max_archives:
                oldest = archives.pop(0)
                os.remove(oldest)
                logger.info(f"Pruned old decision archive: {oldest}")
        except Exception as e:
            logger.warning(f"Failed to prune decision archives: {e}")

    def _record_decision(self, decision: dict):
        """Append decision to ring buffer, JSONL log, and API cache.

        Enriches the decision with structured audit fields before logging.
        Automatically rotates the log file when it exceeds size/line thresholds.
        """
        self._decision_history.append(decision)

        # Rotate log before writing if thresholds exceeded
        self._rotate_decision_log()

        # Build enriched audit record for JSONL — all required fields present
        audit_record = {
            "timestamp": decision.get("timestamp", ""),
            "symbol": decision.get("symbol", "UNKNOWN"),
            "raw_ppo_action": decision.get("ppo_raw_action", []),
            "corrected_action": decision.get("ppo_corrected_action", 0.0),
            "bias": decision.get("ppo_bias", 0.0),
            "regime": decision.get("lstm_regime", "UNKNOWN"),
            "confidence": decision.get("confidence", 0.0),
            "threshold": decision.get("pre_threshold_exposure", 0.0),
            "reason": decision.get("reason", ""),
            "target_exposure": decision.get("exposure", 0.0),
            "model_path": decision.get("model_version", ""),
            "model_version": decision.get("model_version", ""),
            "is_canary": decision.get("is_canary", False),
            "lot_size": decision.get("lot_size", 0.0),
            "sl": decision.get("sl", 0.0),
            "tp": decision.get("tp", 0.0),
            # Preserved for backward-compat; these were in the original schema
            "ppo_primary_action": decision.get("ppo_primary_action", 0.0),
            "action": decision.get("action", "HOLD"),
            "canary_scale": decision.get("canary_scale", 1.0),
            "vol_scale": decision.get("vol_scale", 1.0),
            "risk_can_trade": decision.get("risk_can_trade", False),
            "risk_dd_pct": decision.get("risk_dd_pct", 0.0),
            "regime_trailing": decision.get("regime_trailing", {}),
        }

        try:
            with open(self._decision_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_record, default=str) + "\n")
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
            order_meta = {
                "lane": "canary" if decision.get("is_canary") else "champion",
                "model_version": decision.get("model_version", ""),
            }
            self.executor.reconcile_exposure(
                symbol, decision["exposure"], max_lots,
                max_positions_per_symbol=max_positions_per_symbol,
                order_meta=order_meta,
            )
            if risk_supervisor is not None:
                risk_supervisor.mark_trade(symbol)
        except Exception as e:
            logger.error(f"Execution error for {symbol}: {e}")
            self.risk.record_error(critical=False)  # Don't trigger kill switch for execution errors

        return decision

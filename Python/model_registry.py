import os
import json
import shutil
from datetime import datetime, timezone
from loguru import logger

_EMPTY_ACTIVE = {"champion": None, "canary": None, "symbols": {}}


class ModelRegistry:
    """
    File-based model registry.
    Layout:
      models/
        registry/
          active.json
          champion/<version>/
          canary/<version>/
          candidates/<version>/
          per_symbol/
            {SYMBOL}/
              candidates/<version>/
    """
    def __init__(self, root=None, registry_config=None):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.root = root or os.path.join(base, "models", "registry")
        os.makedirs(self.root, exist_ok=True)

        self.registry_config = registry_config or self._load_registry_config()

        self.active_path = os.path.join(self.root, "active.json")
        self.champion_dir = os.path.join(self.root, "champion")
        self.canary_dir = os.path.join(self.root, "canary")
        self.candidates_dir = os.path.join(self.root, "candidates")
        self.per_symbol_dir = os.path.join(self.root, "per_symbol")

        for d in (self.champion_dir, self.canary_dir, self.candidates_dir, self.per_symbol_dir):
            os.makedirs(d, exist_ok=True)

        if not os.path.exists(self.active_path):
            self._write_active(dict(_EMPTY_ACTIVE))

    def _load_registry_config(self) -> dict:
        """Load registry-related config from the project config.yaml."""
        try:
            import yaml
            cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                return cfg.get("model_registry", {})
        except Exception:
            pass
        return {}

    def _read_active(self):
        """Read active.json, returning a normalized empty state on any error."""
        try:
            if os.path.exists(self.active_path):
                with open(self.active_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    # Ensure required keys
                    data.setdefault("champion", None)
                    data.setdefault("canary", None)
                    data.setdefault("symbols", {})
                    return data
        except (json.JSONDecodeError, ValueError, OSError):
            pass
        # Return normalized empty state for corrupt/missing file
        return dict(_EMPTY_ACTIVE)

    def _write_active(self, payload: dict):
        with open(self.active_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def _timestamp_version(self):
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    def new_candidate_dir(self, tag: str = "candidate") -> str:
        ver = f"{tag}_{self._timestamp_version()}"
        path = os.path.join(self.candidates_dir, ver)
        os.makedirs(path, exist_ok=True)
        return path

    def load_active_model(self, prefer_canary: bool = True, symbol: str = None) -> str | None:
        """
        Get the active model path.
        If symbol is provided, uses per-symbol canary/champion with global fallback.
        Validates that per-symbol artifacts match the requested symbol.
        """
        return self.get_active_model(symbol=symbol, prefer_canary=prefer_canary)

    def set_canary(self, version_dir: str, symbol: str = None):
        """
        Set canary model.
        If symbol is provided, sets per-symbol canary (with symbol artifact validation).
        Otherwise sets global canary.
        """
        active = self._read_active()
        if symbol is not None:
            # Validate that the artifact's declared symbol matches the target symbol
            artifact_symbols = self._read_artifact_symbols(version_dir)
            if artifact_symbols and symbol not in artifact_symbols:
                raise RuntimeError(
                    f"Symbol mismatch: artifact declares symbols {artifact_symbols} "
                    f"but tried to set as canary for {symbol}"
                )
            self._ensure_symbol_entry(active, symbol)
            active["symbols"][symbol]["canary"] = version_dir
            self._write_active(active)
            logger.warning(f"Per-symbol canary set for {symbol}: {version_dir}")
        else:
            active["canary"] = version_dir
            self._write_active(active)
            logger.warning(f"Global canary set: {version_dir}")

    def promote_canary_to_champion(self, symbol: str = None):
        """
        Promote canary to champion.
        If symbol is provided, promotes per-symbol canary with metrics validation.
        Otherwise promotes global canary.
        Requires survival metrics to have been recorded via update_canary_metrics().
        """
        active = self._read_active()
        if symbol is not None:
            self._ensure_symbol_entry(active, symbol)
            canary = active["symbols"][symbol].get("canary")
            if not canary:
                raise RuntimeError(f"No canary to promote for symbol {symbol}.")

            # Validate metrics before promotion
            state = active["symbols"][symbol].get("canary_state", {})
            policy = active["symbols"][symbol].get("canary_policy", {})
            if not self._validate_canary_metrics(state, policy):
                raise RuntimeError(
                    f"Canary for {symbol} has not met promotion thresholds: "
                    f"state={state} policy={policy}"
                )

            old_champ = active["symbols"][symbol].get("champion")
            active["symbols"][symbol]["champion"] = canary
            active["symbols"][symbol]["canary"] = None

            # Track champion history
            history = active["symbols"][symbol].get("champion_history", [])
            if old_champ:
                history.append({
                    "path": old_champ,
                    "replaced_at": datetime.now(timezone.utc).isoformat(),
                    "replaced_by": canary,
                })
            active["symbols"][symbol]["champion_history"] = history
            active["symbols"][symbol]["canary_state"] = {}

            self._write_active(active)
            logger.success(f"Per-symbol canary promoted to champion for {symbol}: {canary}")
        else:
            if not active.get("canary"):
                raise RuntimeError("No canary to promote.")

            # Validate global canary metrics
            state = active.get("canary_state", {})
            policy = active.get("canary_policy", {})
            if not self._validate_canary_metrics(state, policy):
                raise RuntimeError(
                    f"Canary has not met promotion thresholds: "
                    f"state={state} policy={policy}"
                )

            old_champ = active.get("champion")
            active["champion"] = active["canary"]
            active["canary"] = None

            # Track global champion history
            history = active.get("champion_history", [])
            history.append({
                "path": active["champion"],
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "replaced": old_champ,
            })
            active["champion_history"] = history
            active["canary_state"] = {}

            self._write_active(active)
            logger.success(f"Promoted to champion: {active['champion']}")

    def clear_canary(self, symbol: str = None):
        """Clear canary model. If symbol is provided, clears per-symbol canary only."""
        active = self._read_active()
        if symbol is not None:
            self._ensure_symbol_entry(active, symbol)
            active["symbols"][symbol]["canary"] = None
            active["symbols"][symbol]["canary_state"] = {}
            self._write_active(active)
            logger.warning(f"Per-symbol canary cleared for {symbol}")
        else:
            active["canary"] = None
            self._write_active(active)
            logger.warning("Global canary cleared")

    def rollback_to_champion(self, symbol: str = None):
        """Rollback canary to champion. If symbol provided, rolls back per-symbol only."""
        self.clear_canary(symbol=symbol)

    # ── Per-symbol champion/canary management ────────────────────────────

    def _ensure_symbol_entry(self, active: dict, symbol: str) -> dict:
        """Ensure a per-symbol entry exists in active.json and return it."""
        if "symbols" not in active:
            active["symbols"] = {}
        if symbol not in active["symbols"]:
            active["symbols"][symbol] = {
                "champion": None,
                "canary": None,
                "canary_policy": {},
                "canary_state": {},
                "champion_history": [],
            }
        return active

    def _read_artifact_symbols(self, version_dir: str) -> list[str] | None:
        """Read the symbols declared in an artifact's metadata or scorecard."""
        for filename in ("metadata.json", "scorecard.json"):
            path = os.path.join(version_dir, filename)
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    symbols = data.get("symbols") or data.get("symbol")
                    if symbols is not None:
                        if isinstance(symbols, str):
                            return [symbols]
                        if isinstance(symbols, list):
                            return symbols
                except Exception:
                    pass
        return None

    def symbol_candidates_dir(self, symbol: str) -> str:
        """Return (and create) the per-symbol candidates directory."""
        path = os.path.join(self.per_symbol_dir, symbol, "candidates")
        os.makedirs(path, exist_ok=True)
        return path

    def new_symbol_candidate_dir(self, symbol: str, tag: str = "candidate") -> str:
        """Create a timestamped candidate directory under per_symbol/{SYMBOL}/candidates/."""
        ver = f"{tag}_{self._timestamp_version()}"
        path = os.path.join(self.symbol_candidates_dir(symbol), ver)
        os.makedirs(path, exist_ok=True)
        return path

    def set_champion(self, symbol: str, version_dir: str):
        """Set the champion model for a specific symbol."""
        active = self._read_active()
        self._ensure_symbol_entry(active, symbol)
        active["symbols"][symbol]["champion"] = version_dir
        self._write_active(active)
        logger.success(f"Per-symbol champion set for {symbol}: {version_dir}")

    def get_champion(self, symbol: str = None) -> str | None:
        """
        Get champion model path.
        If symbol is provided, returns per-symbol champion with global fallback.
        If symbol is None, returns global champion.
        """
        active = self._read_active()
        if symbol is not None:
            sym_champ = active.get("symbols", {}).get(symbol, {}).get("champion")
            if sym_champ:
                return sym_champ
        return active.get("champion")

    def get_canary(self, symbol: str = None) -> str | None:
        """
        Get canary model path.
        If symbol is provided, returns per-symbol canary with global fallback.
        If symbol is None, returns global canary.
        """
        active = self._read_active()
        if symbol is not None:
            sym_canary = active.get("symbols", {}).get(symbol, {}).get("canary")
            if sym_canary:
                return sym_canary
        return active.get("canary")

    def get_active_model(self, symbol: str = None, prefer_canary: bool = True) -> str | None:
        """
        Get the active model path for a symbol.
        Tries per-symbol canary/champion first, falls back to global.
        Validates that artifacts match the requested symbol.
        """
        if prefer_canary:
            canary = self.get_canary(symbol=symbol)
            if canary:
                # Validate per-symbol artifact matches the requested symbol
                if symbol is not None:
                    artifact_symbols = self._read_artifact_symbols(canary)
                    if artifact_symbols and symbol not in artifact_symbols:
                        logger.warning(
                            f"Per-symbol canary for {symbol} has mismatched artifact symbols "
                            f"{artifact_symbols}, skipping"
                        )
                        # Clear the invalid entry
                        active = self._read_active()
                        self._ensure_symbol_entry(active, symbol)
                        active["symbols"][symbol]["canary"] = None
                        self._write_active(active)
                    else:
                        return canary
                else:
                    return canary

        champion = self.get_champion(symbol=symbol)
        if champion:
            # Validate per-symbol artifact matches the requested symbol
            if symbol is not None:
                artifact_symbols = self._read_artifact_symbols(champion)
                if artifact_symbols and symbol not in artifact_symbols:
                    logger.warning(
                        f"Per-symbol champion for {symbol} has mismatched artifact symbols "
                        f"{artifact_symbols}, skipping"
                    )
                    # Clear the invalid entry
                    active = self._read_active()
                    self._ensure_symbol_entry(active, symbol)
                    active["symbols"][symbol]["champion"] = None
                    self._write_active(active)
                    # Fall through to global champion, but also validate it
                    global_champ = self.get_champion(symbol=None)
                    if global_champ:
                        global_artifact_symbols = self._read_artifact_symbols(global_champ)
                        if global_artifact_symbols and symbol not in global_artifact_symbols:
                            logger.warning(
                                f"Global champion also has mismatched artifact symbols "
                                f"{global_artifact_symbols} for {symbol}, skipping"
                            )
                            return None
                        return global_champ
                    return None
            return champion
        return None

    def is_per_symbol_canary(self, symbol: str, model_dir: str) -> bool:
        """Check if a model directory is the per-symbol canary."""
        active = self._read_active()
        return active.get("symbols", {}).get(symbol, {}).get("canary") == model_dir

    def promote_canary(self, symbol: str):
        """Promote the per-symbol canary to champion for that symbol."""
        active = self._read_active()
        self._ensure_symbol_entry(active, symbol)
        canary = active["symbols"][symbol].get("canary")
        if not canary:
            raise RuntimeError(f"No canary to promote for symbol {symbol}.")

        old_champ = active["symbols"][symbol].get("champion")
        active["symbols"][symbol]["champion"] = canary
        active["symbols"][symbol]["canary"] = None

        # Track champion history
        history = active["symbols"][symbol].get("champion_history", [])
        if old_champ:
            history.append({
                "path": old_champ,
                "replaced_at": datetime.now(timezone.utc).isoformat(),
                "replaced_by": canary,
            })
        active["symbols"][symbol]["champion_history"] = history

        self._write_active(active)
        logger.success(f"Per-symbol canary promoted to champion for {symbol}: {canary}")

    def clear_per_symbol_canary(self, symbol: str):
        """Clear the canary for a specific symbol."""
        active = self._read_active()
        self._ensure_symbol_entry(active, symbol)
        active["symbols"][symbol]["canary"] = None
        active["symbols"][symbol]["canary_state"] = {}
        self._write_active(active)
        logger.warning(f"Per-symbol canary cleared for {symbol}")

    # ── Canary metrics tracking & validation ────────────────────────────

    def update_canary_metrics(self, trades: int, realized_pnl: float,
                              drawdown: float, runtime_minutes: float,
                              symbol: str = None):
        """
        Update survival metrics for the active canary.
        If symbol is provided, updates per-symbol canary state.
        Otherwise updates global canary state.
        """
        active = self._read_active()
        entry = {
            "trades": trades,
            "realized_pnl": realized_pnl,
            "drawdown": drawdown,
            "runtime_minutes": runtime_minutes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if symbol is not None:
            self._ensure_symbol_entry(active, symbol)
            if not active["symbols"][symbol].get("canary"):
                logger.warning(f"No canary set for {symbol}, cannot update metrics")
                return
            # Merge with existing state
            existing = active["symbols"][symbol].get("canary_state", {})
            existing.update(entry)
            active["symbols"][symbol]["canary_state"] = existing
        else:
            if not active.get("canary"):
                logger.warning("No global canary set, cannot update metrics")
                return
            existing = active.get("canary_state", {})
            existing.update(entry)
            active["canary_state"] = existing

        self._write_active(active)
        logger.info(f"Canary metrics updated for {'symbol=' + symbol if symbol else 'global'}: trades={trades} pnl={realized_pnl}")

    def _validate_canary_metrics(self, state: dict, policy: dict) -> bool:
        """
        Check if canary metrics meet the promotion thresholds in policy.
        Metrics must have been recorded (at least 'trades' key) before promotion is allowed.
        """
        # Metrics must be recorded before promotion is allowed
        if not state or "trades" not in state:
            return False

        if not policy:
            return True  # No policy thresholds to check beyond having metrics

        min_trades = policy.get("min_trades", 0)
        min_pnl = policy.get("min_realized_pnl", float("-inf"))
        max_dd = policy.get("max_drawdown", float("inf"))
        min_runtime = policy.get("min_runtime_minutes", 0)

        trades = state.get("trades", 0)
        pnl = state.get("realized_pnl", float("-inf"))
        dd = state.get("drawdown", float("inf"))
        runtime = state.get("runtime_minutes", 0)

        if trades < min_trades:
            return False
        if pnl < min_pnl:
            return False
        if dd > max_dd:
            return False
        if runtime < min_runtime:
            return False

        return True

    # ── Champion history ────────────────────────────────────────────────

    def get_recent_champions(self, symbol: str = None, limit: int = 10) -> list[dict]:
        """
        Return recent champion history entries (newest first).
        If symbol is provided, returns per-symbol history. Otherwise global.
        """
        active = self._read_active()
        if symbol is not None:
            history = active.get("symbols", {}).get(symbol, {}).get("champion_history", [])
        else:
            history = active.get("champion_history", [])
        return list(reversed(history[-limit:]))

    def get_all_symbols(self) -> dict:
        """Return all per-symbol champion/canary mappings."""
        active = self._read_active()
        return active.get("symbols", {})

    def register_candidate(self, candidate_dir: str, metadata: dict):
        meta_path = os.path.join(candidate_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"Candidate registered: {candidate_dir}")

    def save_candidate(self, state_dict, metrics: dict, model_type: str = "lstm") -> str:
        """
        Save a trained model as a candidate for evaluation.
        Called by train_lstm.py after training completes.

        Args:
            state_dict: PyTorch model state_dict
            metrics: dict with training metrics (win_rate, loss, etc.)
            model_type: "lstm" or "ppo"

        Returns:
            Path to the candidate directory.
        """
        import torch

        candidate_dir = self.new_candidate_dir(tag=model_type)

        # Save model weights
        if model_type == "lstm":
            model_path = os.path.join(candidate_dir, "lstm_model.pth")
        else:
            model_path = os.path.join(candidate_dir, "ppo_trading.zip")

        torch.save(state_dict, model_path)

        # Save metadata / scorecard
        metrics["type"] = model_type
        metrics["saved_at"] = datetime.now(timezone.utc).isoformat()
        scorecard_path = os.path.join(candidate_dir, "scorecard.json")
        with open(scorecard_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        self.register_candidate(candidate_dir, metrics)
        logger.success(f"Candidate saved: {candidate_dir} (type={model_type})")
        return candidate_dir

    def evaluate_and_stage_canary(self, candidate_dir: str) -> bool:
        """
        Quick evaluation gate: check if a candidate's scorecard passes
        minimum thresholds to be staged as canary.
        Called by train_lstm.py after saving a candidate.

        Returns True if candidate was promoted to canary.
        """
        scorecard_path = os.path.join(candidate_dir, "scorecard.json")
        if not os.path.exists(scorecard_path):
            logger.warning(f"No scorecard found at {candidate_dir}")
            return False

        with open(scorecard_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)

        model_type = metrics.get("type", "lstm")
        win_rate = metrics.get("win_rate", 0.0)
        loss = metrics.get("loss", float("inf"))

        # PPO candidates: stage as canary, auto-promote if no champion exists
        if model_type == "ppo":
            active = self._read_active()
            if not active.get("champion"):
                # No champion yet — promote directly so trading can begin
                active["champion"] = candidate_dir
                active["canary"] = None
                self._write_active(active)
                logger.success(f"No existing champion — PPO candidate auto-promoted to champion: {candidate_dir}")
            else:
                self.set_canary(candidate_dir)
                logger.success(f"PPO candidate staged as canary for live eval")
            return True

        # LSTM candidates: meaningful quality thresholds for canary staging
        # Raw accuracy is misleading with class imbalance, so we require macro F1
        # and minimum per-class recall to ensure all regimes are detected
        macro_f1 = metrics.get("macro_f1", 0.0)
        per_class = metrics.get("per_class", {})
        min_recall = min(
            (per_class.get(cls, {}).get("recall", 0.0) for cls in ["LOW_VOL", "MED_VOL", "HIGH_VOL"]),
            default=0.0
        )
        if macro_f1 >= 0.40 and min_recall >= 0.10 and loss < 2.0:
            self.set_canary(candidate_dir)
            logger.success(f"Candidate staged as canary: macro_f1={macro_f1:.3f} min_recall={min_recall:.2f} loss={loss:.4f}")
            return True
        else:
            logger.info(f"Candidate did not pass canary gate: macro_f1={macro_f1:.3f} min_recall={min_recall:.2f} loss={loss:.4f}")
            return False

    def read_metadata(self, version_dir: str) -> dict:
        meta_path = os.path.join(version_dir, "metadata.json")
        if not os.path.exists(meta_path):
            return {}
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)

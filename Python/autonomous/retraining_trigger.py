"""
RetrainingTrigger — decides when the feedback loop has accumulated
enough evidence to justify a new training cycle.

Triggers:
  - 50 new closed demo trades
  - 100 blocked trades
  - champion drawdown warning
  - regime performance degradation
  - feature drift detected
  - model confidence calibration drift
  - new MT5 data window
  - candidate beats champion in validation

Output: trigger artifact with retraining_trigger_id, triggered, reasons,
next_cycle_command.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from loguru import logger


@dataclass
class TriggerArtifact:
    retraining_trigger_id: str
    triggered: bool
    reasons: List[str] = field(default_factory=list)
    next_cycle_command: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class RetrainingTrigger:
    """
    Stateful trigger that evaluates whether the system should enter
    a new training / champion-promotion cycle.
    """

    def __init__(
        self,
        data_dir: str = "logs",
        thresholds: Optional[Dict[str, Any]] = None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.thresholds = {
            "min_closed_demo_trades": 50,
            "min_blocked_trades": 100,
            "champion_drawdown_pct": 5.0,
            "regime_degradation_win_rate": 0.35,
            "confidence_calibration_mae": 0.15,
            "feature_drift_psi": 0.25,
            "validation_beat_champion_margin": 0.02,
            **(thresholds or {}),
        }

        # Counters (persisted to JSON on evaluate)
        self.closed_demo_trade_count: int = 0
        self.blocked_trade_count: int = 0
        self.last_trigger_time: Optional[str] = None

    # ------------------------------------------------------------------
    # Incremental counters
    # ------------------------------------------------------------------
    def increment_closed_demo(self, n: int = 1) -> None:
        self.closed_demo_trade_count += n

    def increment_blocked(self, n: int = 1) -> None:
        self.blocked_trade_count += n

    # ------------------------------------------------------------------
    # Evaluation inputs
    # ------------------------------------------------------------------
    def evaluate(
        self,
        champion_drawdown_pct: Optional[float] = None,
        regime_win_rates: Optional[Dict[str, float]] = None,
        feature_drift_psi: Optional[float] = None,
        confidence_calibration_mae: Optional[float] = None,
        new_mt5_data_available: bool = False,
        candidate_beats_champion: Optional[float] = None,
        canary_artifact: Optional[Dict[str, Any]] = None,
    ) -> TriggerArtifact:
        """
        Run all trigger rules and return a TriggerArtifact.
        """
        now = datetime.now(timezone.utc)
        reasons: List[str] = []

        # 1. Demo trade volume
        if self.closed_demo_trade_count >= self.thresholds["min_closed_demo_trades"]:
            reasons.append(
                f"closed_demo_trades {self.closed_demo_trade_count} >= {self.thresholds['min_closed_demo_trades']}"
            )

        # 2. Blocked trade volume
        if self.blocked_trade_count >= self.thresholds["min_blocked_trades"]:
            reasons.append(
                f"blocked_trades {self.blocked_trade_count} >= {self.thresholds['min_blocked_trades']}"
            )

        # 3. Champion drawdown warning
        if champion_drawdown_pct is not None:
            if champion_drawdown_pct >= self.thresholds["champion_drawdown_pct"]:
                reasons.append(
                    f"champion_drawdown {champion_drawdown_pct:.2f}% >= {self.thresholds['champion_drawdown_pct']}%"
                )

        # 4. Regime degradation
        if regime_win_rates:
            for regime, wr in regime_win_rates.items():
                if wr < self.thresholds["regime_degradation_win_rate"]:
                    reasons.append(
                        f"regime '{regime}' win_rate {wr:.2f} < {self.thresholds['regime_degradation_win_rate']}"
                    )

        # 5. Feature drift
        if feature_drift_psi is not None:
            if feature_drift_psi >= self.thresholds["feature_drift_psi"]:
                reasons.append(
                    f"feature_drift PSI {feature_drift_psi:.3f} >= {self.thresholds['feature_drift_psi']}"
                )

        # 6. Confidence calibration drift
        if confidence_calibration_mae is not None:
            if confidence_calibration_mae >= self.thresholds["confidence_calibration_mae"]:
                reasons.append(
                    f"confidence_calibration MAE {confidence_calibration_mae:.3f} >= {self.thresholds['confidence_calibration_mae']}"
                )

        # 7. New MT5 data window
        if new_mt5_data_available:
            reasons.append("new_mt5_data_window available")

        # 8. Candidate beats champion in validation
        if candidate_beats_champion is not None:
            margin = self.thresholds["validation_beat_champion_margin"]
            if candidate_beats_champion >= margin:
                reasons.append(
                    f"candidate_beats_champion by {candidate_beats_champion:.3f} >= {margin}"
                )

        # 9. Canary promotion signal
        if canary_artifact:
            if canary_artifact.get("approved_for_champion") and not canary_artifact.get("approved_for_real_live"):
                reasons.append("canary approved_for_champion but not yet for real-live")

        triggered = len(reasons) > 0

        next_cycle_command = ""
        if triggered:
            if candidate_beats_champion is not None:
                next_cycle_command = "run_champion_promotion"
            elif canary_artifact and canary_artifact.get("approved_for_real_live"):
                next_cycle_command = "promote_to_real_live"
            elif new_mt5_data_available or self.closed_demo_trade_count >= self.thresholds["min_closed_demo_trades"]:
                next_cycle_command = "run_retraining"
            else:
                next_cycle_command = "run_evaluation"

        artifact = TriggerArtifact(
            retraining_trigger_id=f"trigger_{uuid.uuid4().hex[:8]}",
            triggered=triggered,
            reasons=reasons,
            next_cycle_command=next_cycle_command,
            metadata={
                "evaluated_at": now.isoformat(),
                "closed_demo_trade_count": self.closed_demo_trade_count,
                "blocked_trade_count": self.blocked_trade_count,
                "champion_drawdown_pct": champion_drawdown_pct,
                "feature_drift_psi": feature_drift_psi,
                "confidence_calibration_mae": confidence_calibration_mae,
                "candidate_beats_champion": candidate_beats_champion,
            },
        )

        # Persist
        path = self.data_dir / f"{artifact.retraining_trigger_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(artifact), f, indent=2)

        if triggered:
            logger.info(
                f"RetrainingTrigger {artifact.retraining_trigger_id} triggered: {reasons} -> {next_cycle_command}"
            )
            self.last_trigger_time = now.isoformat()
            # Reset counters after trigger so we don't double-fire
            self.closed_demo_trade_count = 0
            self.blocked_trade_count = 0
        else:
            logger.debug(f"RetrainingTrigger not triggered at {now.isoformat()}")

        return artifact

    def get_last_trigger(self) -> Optional[Dict[str, Any]]:
        """Return the most recent trigger artifact from disk."""
        files = sorted(self.data_dir.glob("trigger_*.json"), reverse=True)
        if not files:
            return None
        with open(files[0], "r", encoding="utf-8") as f:
            return json.load(f)

"""PromotionGates — comprehensive gate system for model bundle promotion."""
from __future__ import annotations

import os
from typing import Optional

try:
    from loguru import logger
except ImportError:
    import logging as _logging
    logger = _logging.getLogger("promotion_gates")  # type: ignore


class PromotionGates:
    """Validate a model bundle against data, training, performance, stability,
    baseline, canary, and safety gates before promotion.
    """

    DEFAULT_GATES = {
        "min_oos_return": 0.02,
        "min_profit_factor": 1.15,
        "min_sharpe": 0.50,
        "max_drawdown": 0.08,
        "min_trade_count": 50,
        "max_single_trade_profit_share": 0.20,
        "min_walk_forward_windows_passed": 3,
        "min_demo_canary_trades": 50,
        "min_demo_canary_days": 7,
        "min_timesteps": 10000,
    }

    def __init__(self, config: Optional[dict] = None):
        self.cfg = dict(config or {})
        self.gates = {**self.DEFAULT_GATES, **self.cfg.get("promotion_gates", {})}

    def evaluate(self, bundle_id: str, validation_report: dict) -> tuple[bool, list[str]]:
        """Run all gates and return (passed, reasons)."""
        reasons: list[str] = []

        # ── Data gates ────────────────────────────────────────────────────
        self._run_data_gates(validation_report, reasons)

        # ── Training gates ────────────────────────────────────────────────
        self._run_training_gates(validation_report, reasons)

        # ── Performance gates ───────────────────────────────────────────
        self._run_performance_gates(validation_report, reasons)

        # ── Stability gates ─────────────────────────────────────────────
        self._run_stability_gates(validation_report, reasons)

        # ── Baseline gates ──────────────────────────────────────────────
        self._run_baseline_gates(validation_report, reasons)

        # ── Canary gates ────────────────────────────────────────────────
        self._run_canary_gates(validation_report, reasons)

        # ── Safety gates ────────────────────────────────────────────────
        self._run_safety_gates(validation_report, reasons)

        passed = len(reasons) == 0
        if passed:
            logger.success(f"PromotionGates passed for bundle {bundle_id}")
        else:
            logger.warning(f"PromotionGates failed for bundle {bundle_id}: {reasons}")
        return passed, reasons

    # ------------------------------------------------------------------
    # Data gates
    # ------------------------------------------------------------------
    def _run_data_gates(self, report: dict, reasons: list[str]) -> None:
        meta = report.get("metadata", {})
        scorecard = report.get("scorecard", {})

        data_source = str(meta.get("data_source") or scorecard.get("data_source") or "unknown").lower()
        if data_source != "mt5":
            reasons.append(f"data_source_fail:{data_source}!=mt5")

        if not report.get("has_spread_data", False):
            reasons.append("missing_spread_data")

        if report.get("leakage_detected", False):
            reasons.append("data_leakage_detected")

        if not report.get("feature_audit_passed", False):
            reasons.append("feature_audit_failed")

    # ------------------------------------------------------------------
    # Training gates
    # ------------------------------------------------------------------
    def _run_training_gates(self, report: dict, reasons: list[str]) -> None:
        meta = report.get("metadata", {})
        scorecard = report.get("scorecard", {})

        timesteps = int(meta.get("timesteps") or scorecard.get("timesteps") or 0)
        if timesteps < self.gates["min_timesteps"]:
            reasons.append(f"timesteps_fail:{timesteps}<{self.gates['min_timesteps']}")

        if not report.get("seed_logged", False):
            reasons.append("seed_not_logged")

        if not (meta.get("dataset_id") or scorecard.get("dataset_id")):
            reasons.append("missing_dataset_id")

        if not (meta.get("feature_set_id") or scorecard.get("feature_set_id")):
            reasons.append("missing_feature_set_id")

        if not report.get("model_bundle_present", False):
            reasons.append("model_bundle_missing")

    # ------------------------------------------------------------------
    # Performance gates
    # ------------------------------------------------------------------
    def _run_performance_gates(self, report: dict, reasons: list[str]) -> None:
        perf = report.get("performance", {})
        oos_return = float(perf.get("return_after_costs", -999.0))
        profit_factor = float(perf.get("profit_factor", 0.0))
        sharpe = float(perf.get("sharpe", -999.0))
        drawdown = float(perf.get("max_drawdown", 999.0))
        trade_count = int(perf.get("trade_count", 0))
        max_single_share = float(perf.get("max_single_trade_profit_share", 999.0))

        if oos_return <= self.gates["min_oos_return"]:
            reasons.append(f"oos_return_fail:{oos_return:.4f}<={self.gates['min_oos_return']}")

        if profit_factor < self.gates["min_profit_factor"]:
            reasons.append(f"profit_factor_fail:{profit_factor:.2f}<{self.gates['min_profit_factor']}")

        if sharpe < self.gates["min_sharpe"]:
            reasons.append(f"sharpe_fail:{sharpe:.2f}<{self.gates['min_sharpe']}")

        if drawdown > self.gates["max_drawdown"]:
            reasons.append(f"drawdown_fail:{drawdown:.4f}>{self.gates['max_drawdown']}")

        if trade_count < self.gates["min_trade_count"]:
            reasons.append(f"trade_count_fail:{trade_count}<{self.gates['min_trade_count']}")

        if max_single_share > self.gates["max_single_trade_profit_share"]:
            reasons.append(
                f"single_trade_share_fail:{max_single_share:.2f}>{self.gates['max_single_trade_profit_share']}"
            )

    # ------------------------------------------------------------------
    # Stability gates
    # ------------------------------------------------------------------
    def _run_stability_gates(self, report: dict, reasons: list[str]) -> None:
        stability = report.get("stability", {})
        windows_passed = int(stability.get("walk_forward_windows_passed", 0))

        if windows_passed < self.gates["min_walk_forward_windows_passed"]:
            reasons.append(
                f"walk_forward_fail:{windows_passed}<{self.gates['min_walk_forward_windows_passed']}"
            )

        if not report.get("regime_breakdown_present", False):
            reasons.append("missing_regime_breakdown")

        if not stability.get("stress_test_passed", False):
            reasons.append("stress_test_failed")

    # ------------------------------------------------------------------
    # Baseline gates
    # ------------------------------------------------------------------
    def _run_baseline_gates(self, report: dict, reasons: list[str]) -> None:
        baseline = report.get("baseline", {})
        if not baseline.get("beats_random_policy", False):
            reasons.append("fails_vs_random_policy")

        if not baseline.get("beats_buy_and_hold", False):
            reasons.append("fails_vs_buy_and_hold")

        if not baseline.get("beats_previous_champion", False):
            reasons.append("fails_vs_previous_champion")

    # ------------------------------------------------------------------
    # Canary gates
    # ------------------------------------------------------------------
    def _run_canary_gates(self, report: dict, reasons: list[str]) -> None:
        canary = report.get("canary", {})
        if not canary.get("demo_canary_completed", False):
            reasons.append("demo_canary_not_completed")

        demo_trades = int(canary.get("demo_trades", 0))
        if demo_trades < self.gates["min_demo_canary_trades"]:
            reasons.append(f"demo_trades_fail:{demo_trades}<{self.gates['min_demo_canary_trades']}")

        demo_days = int(canary.get("demo_days", 0))
        if demo_days < self.gates["min_demo_canary_days"]:
            reasons.append(f"demo_days_fail:{demo_days}<{self.gates['min_demo_canary_days']}")

        demo_pnl = float(canary.get("demo_pnl_after_costs", -999.0))
        if demo_pnl <= 0.0:
            reasons.append(f"demo_pnl_fail:{demo_pnl:.4f}<=0")

    # ------------------------------------------------------------------
    # Safety gates
    # ------------------------------------------------------------------
    def _run_safety_gates(self, report: dict, reasons: list[str]) -> None:
        safety = report.get("safety", {})
        tests_passing = safety.get("tests_passing", False)
        tests_documented = safety.get("tests_documented", False)

        if not (tests_passing or tests_documented):
            reasons.append("tests_missing_or_failing")

        if not safety.get("account_telemetry_valid", False):
            reasons.append("account_telemetry_invalid")

        if not safety.get("real_money_locked", True):
            reasons.append("real_money_not_locked")

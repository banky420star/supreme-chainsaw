"""Unit tests for PipelineOrchestrator.stage_promotion_gates() decision logic.

Tests verify the promotion gate rules:
- Required: backtest_court, walk_forward, baseline_comparison, overnight_validation
- Optional (warn but don't block): profitability_analysis, symbol_simulations
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure we can import from the project
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = str(PROJECT_ROOT)
if CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)

from Python.autonomous.run_cycle import (
    PipelineOrchestrator,
    _ensure_dirs,
    _ARTIFACTS_ROOT,
    _REPORTS_ROOT,
)


@pytest.fixture
def orch():
    """Create a fresh PipelineOrchestrator with minimal setup.

    Cleans promotion_gates artifacts and registry reports between tests
    so that _artifact_exists_and_valid doesn't cause skips.
    """
    _ensure_dirs()

    # Clean any artifacts/reports from previous tests to prevent skip via caching
    for d in [
        os.path.join(_ARTIFACTS_ROOT, "promotion_gates"),
        os.path.join(_REPORTS_ROOT, "registry"),
    ]:
        if os.path.isdir(d):
            for fname in os.listdir(d):
                fpath = os.path.join(d, fname)
                if os.path.isfile(fpath):
                    os.remove(fpath)

    o = PipelineOrchestrator(
        symbol="EURUSDm",
        timeframe="M15",
        mode="demo-canary",
        require_mt5=False,
        timesteps=1000,
        feature_set_id="test_features",
        dataset_id="test_dataset",
    )
    # Reset state to avoid any pollution from previous tests
    o.state = {"ok": True, "stopped_at": None, "stages": {}}
    return o


def _set_stage(orch: PipelineOrchestrator, stage: str, ok: bool):
    """Helper to set a stage result in the orchestrator state."""
    orch.state.setdefault("stages", {})[stage] = {"ok": ok}


def _run_promotion_gates(orch: PipelineOrchestrator) -> dict:
    """Run stage_promotion_gates and extract the inner result dict.

    The outer _run_stage wrapper checks artifacts, runs the inner _run(),
    and wraps the result. We return the result as-is (it contains ok,
    decision, issues).
    """
    result = orch.stage_promotion_gates()
    return result


# ═══════════════════════════════════════════════════════════════════════
# ALL REQUIRED + ALL OPTIONAL — pass
# ═══════════════════════════════════════════════════════════════════════


class TestAllRequiredPass:
    """All four required stages pass. Optional stages may be anything."""

    def test_all_passes(self, orch):
        """All required + all optional pass → decision = demo_canary."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", True)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", True)
        _set_stage(orch, "profitability_analysis", True)
        _set_stage(orch, "symbol_simulations", True)

        result = _run_promotion_gates(orch)
        assert result["ok"] is True
        assert result["decision"] == "demo_canary"
        # All optional passed, so no optional warning
        assert not any("Optional" in i for i in result.get("issues", []))

    def test_required_pass_optional_fail(self, orch):
        """All required pass, optional fail → demo_canary with warning."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", True)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", True)
        _set_stage(orch, "profitability_analysis", False)
        _set_stage(orch, "symbol_simulations", False)

        result = _run_promotion_gates(orch)
        assert result["ok"] is True, "Optional failures should not block"
        assert result["decision"] == "demo_canary"
        # Should warn about optional stages
        optional_issues = [i for i in result.get("issues", []) if "Optional" in i]
        assert len(optional_issues) >= 1
        assert "profitability_analysis" in optional_issues[0]
        assert "symbol_simulations" in optional_issues[0]

    def test_required_pass_one_optional_fail(self, orch):
        """All required pass, one optional fails → demo_canary."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", True)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", True)
        _set_stage(orch, "profitability_analysis", True)
        _set_stage(orch, "symbol_simulations", False)

        result = _run_promotion_gates(orch)
        assert result["ok"] is True
        assert result["decision"] == "demo_canary"
        optional_issues = [i for i in result.get("issues", []) if "Optional" in i]
        assert len(optional_issues) >= 1


# ═══════════════════════════════════════════════════════════════════════
# SOME REQUIRED FAIL
# ═══════════════════════════════════════════════════════════════════════


class TestRequiredFail:
    """At least one required stage fails → reject."""

    def test_overnight_validation_fails(self, orch):
        """overnight_validation is required — if it fails, reject."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", True)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", False)

        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"
        assert "overnight_validation" in str(result.get("issues", []))

    def test_backtest_court_fails(self, orch):
        """Original required gate — if it fails, reject."""
        _set_stage(orch, "backtest_court", False)
        _set_stage(orch, "walk_forward", True)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", True)

        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"
        assert "backtest_court" in str(result.get("issues", []))

    def test_walk_forward_fails(self, orch):
        """walk_forward is required — if it fails, reject."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", False)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", True)

        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"
        assert "walk_forward" in str(result.get("issues", []))

    def test_baseline_comparison_fails(self, orch):
        """baseline_comparison is required — if it fails, reject."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", True)
        _set_stage(orch, "baseline_comparison", False)
        _set_stage(orch, "overnight_validation", True)

        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"
        assert "baseline_comparison" in str(result.get("issues", []))

    def test_all_required_fail(self, orch):
        """All required fail → reject with all named."""
        _set_stage(orch, "backtest_court", False)
        _set_stage(orch, "walk_forward", False)
        _set_stage(orch, "baseline_comparison", False)
        _set_stage(orch, "overnight_validation", False)

        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"
        for s in ["backtest_court", "walk_forward", "baseline_comparison", "overnight_validation"]:
            assert s in str(result.get("issues", []))

    def test_two_required_fail(self, orch):
        """Two of four required fail → reject with specific names."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", False)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", False)

        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"
        assert "walk_forward" in str(result.get("issues", []))
        assert "overnight_validation" in str(result.get("issues", []))
        assert "backtest_court" not in str(result.get("issues", []))
        assert "baseline_comparison" not in str(result.get("issues", []))


# ═══════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Boundary conditions and missing state scenarios."""

    def test_no_stages_in_state(self, orch):
        """No stages have run yet → all default to False → reject."""
        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"

    def test_only_optional_stages_in_state(self, orch):
        """Only optional stages present but no required → reject."""
        _set_stage(orch, "profitability_analysis", True)
        _set_stage(orch, "symbol_simulations", True)

        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"

    def test_required_pass_missing_optional(self, orch):
        """Required pass, optional not in state at all → promote with warning."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", True)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", True)
        # Optional stages not in state → defaults to False

        result = _run_promotion_gates(orch)
        assert result["ok"] is True
        assert result["decision"] == "demo_canary"
        optional_issues = [i for i in result.get("issues", []) if "Optional" in i]
        assert len(optional_issues) >= 1

    def test_empty_stages_dict(self, orch):
        """stages key exists but is empty → all False → reject."""
        orch.state["stages"] = {}
        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"

    def test_partial_stage_result(self, orch):
        """Stage exists but has no 'ok' key → defaults to False."""
        orch.state.setdefault("stages", {})["backtest_court"] = {"status": "done"}
        result = _run_promotion_gates(orch)
        assert result["ok"] is False
        assert result["decision"] == "reject"


# ═══════════════════════════════════════════════════════════════════════
# REPORT OUTPUT
# ═══════════════════════════════════════════════════════════════════════


class TestReportOutput:
    """Verify the report JSON contains correct upstream/optional fields."""

    def _check_decision_file(self, orch, expected_decision: str):
        """Read the PROMOTION_DECISION.json report and verify its contents."""
        report_dir = os.path.join(CORE_PATH, "reports", "registry")
        report_path = os.path.join(report_dir, "PROMOTION_DECISION.json")
        assert os.path.exists(report_path), f"Report not found at {report_path}"
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["decision"] == expected_decision
        assert data["symbol"] == orch.symbol
        assert data["timeframe"] == orch.timeframe
        # upstream dict must have overnight_validation
        assert "overnight_validation" in data.get("upstream", {})
        # optional dict must exist
        assert "optional" in data
        assert "profitability_analysis" in data["optional"]
        assert "symbol_simulations" in data["optional"]
        return data

    def test_report_all_pass(self, orch):
        """Report includes overnight_validation in upstream and optional block."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", True)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", True)
        _set_stage(orch, "profitability_analysis", True)
        _set_stage(orch, "symbol_simulations", True)

        _run_promotion_gates(orch)
        data = self._check_decision_file(orch, "demo_canary")
        assert data["upstream"]["overnight_validation"] is True
        assert data["optional"]["profitability_analysis"] is True
        assert data["optional"]["symbol_simulations"] is True

    def test_report_some_fail(self, orch):
        """Report correctly reflects failed stages."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", False)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", False)
        _set_stage(orch, "profitability_analysis", False)
        _set_stage(orch, "symbol_simulations", True)

        _run_promotion_gates(orch)
        data = self._check_decision_file(orch, "reject")
        assert data["upstream"]["walk_forward"] is False
        assert data["upstream"]["overnight_validation"] is False
        assert data["optional"]["profitability_analysis"] is False
        assert data["optional"]["symbol_simulations"] is True

    def test_report_missing_stages(self, orch):
        """Report defaults to False for stages not in state."""
        _set_stage(orch, "backtest_court", True)
        _set_stage(orch, "walk_forward", True)
        _set_stage(orch, "baseline_comparison", True)
        _set_stage(orch, "overnight_validation", True)
        # No optional stages in state

        _run_promotion_gates(orch)
        data = self._check_decision_file(orch, "demo_canary")
        assert data["optional"]["profitability_analysis"] is False
        assert data["optional"]["symbol_simulations"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

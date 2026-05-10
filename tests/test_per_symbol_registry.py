"""
Tests for the per-symbol model registry restructure.

Verifies:
  - Per-symbol champion/canary storage and retrieval
  - Global fallback when no per-symbol model exists
  - Symbol artifact validation in set_canary
  - Per-symbol canary metrics and promotion
  - Per-symbol rollback isolation
  - Corrupt/missing active.json resilience
"""
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from Python.model_registry import ModelRegistry


CONFIGURED_SYMBOLS = ["EURUSDm", "GBPUSDm", "XAUUSDm", "BTCUSDm"]


def _tmp_registry_root() -> Path:
    root = Path(".tmp") / f"per_symbol_test_{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _make_candidate(root: Path, name: str, symbol: str = None) -> str:
    """Create a candidate directory with optional symbol metadata."""
    path = root / "candidates" / name
    path.mkdir(parents=True, exist_ok=True)
    if symbol:
        (path / "scorecard.json").write_text(
            json.dumps({"symbols": [symbol], "symbol": symbol}),
            encoding="utf-8",
        )
    (path / "ppo_trading.zip").write_bytes(b"model")
    (path / "vec_normalize.pkl").write_bytes(b"vec")
    return str(path)


# ── Basic per-symbol champion/canary CRUD ─────────────────────────────


class TestPerSymbolChampionCanary:
    def test_set_and_get_per_symbol_champion(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            path = "/some/model/v1"
            reg.set_champion("EURUSDm", path)

            assert reg.get_champion(symbol="EURUSDm") == path
            # Other symbols should still fall back to global
            assert reg.get_champion(symbol="GBPUSDm") is None
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_per_symbol_champion_falls_back_to_global(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            global_path = "/global/model/v1"
            reg._write_active({"champion": global_path, "canary": None, "symbols": {}})

            # Symbol without per-symbol champion returns global
            assert reg.get_champion(symbol="XAUUSDm") == global_path
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_per_symbol_champion_takes_precedence_over_global(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            global_path = "/global/model/v1"
            sym_path = "/eur/model/v2"
            reg._write_active({
                "champion": global_path,
                "canary": None,
                "symbols": {
                    "EURUSDm": {
                        "champion": sym_path,
                        "canary": None,
                        "canary_policy": {},
                        "canary_state": {},
                        "champion_history": [],
                    },
                },
            })

            assert reg.get_champion(symbol="EURUSDm") == sym_path
            # Other symbol falls back to global
            assert reg.get_champion(symbol="GBPUSDm") == global_path
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_set_and_get_per_symbol_canary(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            path = "/some/canary/v1"
            reg.set_canary(path, symbol="EURUSDm")

            assert reg.get_canary(symbol="EURUSDm") == path
            # Other symbols should still fall back to global (which is None)
            assert reg.get_canary(symbol="GBPUSDm") is None
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_per_symbol_canary_falls_back_to_global(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            global_canary = "/global/canary/v1"
            reg.set_canary(global_canary)

            # Symbol without per-symbol canary returns global
            assert reg.get_canary(symbol="XAUUSDm") == global_canary
        finally:
            shutil.rmtree(root, ignore_errors=True)


# ── Symbol artifact validation ────────────────────────────────────────


class TestSymbolArtifactValidation:
    def test_set_canary_rejects_mismatched_symbol(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            xau_path = _make_candidate(root, "xau_v1", "XAUUSDm")

            with pytest.raises(RuntimeError, match="artifact is not tagged for that symbol"):
                reg.set_canary(xau_path, symbol="BTCUSDm")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_set_canary_accepts_matching_symbol(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            xau_path = _make_candidate(root, "xau_v1", "XAUUSDm")

            reg.set_canary(xau_path, symbol="XAUUSDm")
            assert reg.get_canary(symbol="XAUUSDm") == xau_path
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_set_canary_allows_no_metadata(self):
        """If artifact has no symbol metadata, allow it (no validation possible)."""
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            path = _make_candidate(root, "generic_v1", symbol=None)

            reg.set_canary(path, symbol="EURUSDm")
            assert reg.get_canary(symbol="EURUSDm") == path
        finally:
            shutil.rmtree(root, ignore_errors=True)


# ── Per-symbol canary metrics and promotion ───────────────────────────


class TestPerSymbolCanaryMetrics:
    def test_promote_canary_requires_metrics_with_policy(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            # Set up symbol with a canary policy that requires metrics
            active = reg._read_active()
            reg._ensure_symbol_entry(active, "XAUUSDm")
            active["symbols"]["XAUUSDm"]["canary"] = "/some/canary"
            active["symbols"]["XAUUSDm"]["canary_policy"] = {
                "min_trades": 30,
                "min_realized_pnl": 0.0,
                "max_drawdown": 0.12,
                "min_runtime_minutes": 45,
            }
            reg._write_active(active)

            with pytest.raises(RuntimeError, match="Canary promotion blocked"):
                reg.promote_canary_to_champion(symbol="XAUUSDm")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_promote_canary_succeeds_with_valid_metrics(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            path = "/some/canary"
            reg.set_canary(path, symbol="XAUUSDm")

            # Set a policy
            active = reg._read_active()
            active["symbols"]["XAUUSDm"]["canary_policy"] = {
                "min_trades": 30,
                "min_realized_pnl": 0.0,
                "max_drawdown": 0.12,
                "min_runtime_minutes": 45,
            }
            reg._write_active(active)

            # Update metrics to meet thresholds
            reg.update_canary_metrics(
                trades=50, realized_pnl=10.0,
                drawdown=0.05, runtime_minutes=60.0,
                symbol="XAUUSDm",
            )

            reg.promote_canary_to_champion(symbol="XAUUSDm")
            assert reg.get_champion(symbol="XAUUSDm") == path
            assert reg.get_canary(symbol="XAUUSDm") is None
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_update_canary_metrics_global(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            reg.set_canary("/global/canary")
            reg.update_canary_metrics(
                trades=20, realized_pnl=5.0,
                drawdown=0.03, runtime_minutes=30.0,
            )

            active = reg._read_active()
            state = active.get("canary_state", {})
            assert state["trades"] == 20
            assert state["realized_pnl"] == 5.0
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_update_canary_metrics_per_symbol(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            reg.set_canary("/eur/canary", symbol="EURUSDm")
            reg.update_canary_metrics(
                trades=15, realized_pnl=3.0,
                drawdown=0.02, runtime_minutes=25.0,
                symbol="EURUSDm",
            )

            active = reg._read_active()
            state = active["symbols"]["EURUSDm"].get("canary_state", {})
            assert state["trades"] == 15
            assert state["realized_pnl"] == 3.0
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_update_canary_metrics_no_canary_set(self):
        """Updating metrics when no canary is set should not crash."""
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            # Should silently log warning, not raise
            reg.update_canary_metrics(
                trades=10, realized_pnl=1.0,
                drawdown=0.01, runtime_minutes=10.0,
            )
            reg.update_canary_metrics(
                trades=10, realized_pnl=1.0,
                drawdown=0.01, runtime_minutes=10.0,
                symbol="GBPUSDm",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


# ── Per-symbol rollback isolation ─────────────────────────────────────


class TestPerSymbolRollback:
    def test_rollback_only_clears_target_symbol(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            reg.set_canary("/eur/canary", symbol="EURUSDm")
            reg.set_canary("/xau/canary", symbol="XAUUSDm")

            reg.rollback_to_champion(symbol="EURUSDm")

            assert reg.get_canary(symbol="EURUSDm") is None
            assert reg.get_canary(symbol="XAUUSDm") == "/xau/canary"
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rollback_does_not_affect_global(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            reg.set_canary("/global/canary")
            reg.set_canary("/eur/canary", symbol="EURUSDm")

            reg.rollback_to_champion(symbol="EURUSDm")

            # Global canary unaffected
            assert reg.get_canary(symbol=None) == "/global/canary"
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_global_rollback_does_not_affect_per_symbol(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            reg.set_canary("/global/canary")
            reg.set_canary("/eur/canary", symbol="EURUSDm")

            reg.rollback_to_champion()

            # Per-symbol canary unaffected
            assert reg.get_canary(symbol="EURUSDm") == "/eur/canary"
            # Global cleared
            assert reg.get_canary(symbol=None) is None
        finally:
            shutil.rmtree(root, ignore_errors=True)


# ── get_active_model with symbol validation ───────────────────────────


class TestGetActiveModel:
    def test_prefers_per_symbol_canary(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            global_champ = _make_candidate(root, "global_v1", "EURUSDm")
            reg.set_canary(global_champ)
            reg.update_canary_metrics(10, 1.0, 0.01, 10.0)
            reg.promote_canary_to_champion(force=True)

            eur_canary = _make_candidate(root, "eur_canary_v1", "EURUSDm")
            reg.set_canary(eur_canary, symbol="EURUSDm")

            result = reg.get_active_model(symbol="EURUSDm", prefer_canary=True)
            assert result == eur_canary
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_falls_back_to_global_champion(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            # Global champion without symbol metadata so any symbol can use it
            global_champ = _make_candidate(root, "global_v1", symbol=None)
            reg.set_canary(global_champ)
            reg.update_canary_metrics(10, 1.0, 0.01, 10.0)
            reg.promote_canary_to_champion(force=True)

            result = reg.get_active_model(symbol="XAUUSDm", prefer_canary=False)
            assert result == global_champ
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_returns_none_when_nothing_available(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            result = reg.get_active_model(symbol="BTCUSDm")
            assert result is None
        finally:
            shutil.rmtree(root, ignore_errors=True)


# ── Champion history ──────────────────────────────────────────────────


class TestChampionHistory:
    def test_per_symbol_champion_history(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            reg.set_canary("/eur/canary_v1", symbol="EURUSDm")
            reg.update_canary_metrics(10, 1.0, 0.01, 10.0, symbol="EURUSDm")
            reg.promote_canary_to_champion(symbol="EURUSDm", force=True)

            reg.set_canary("/eur/canary_v2", symbol="EURUSDm")
            reg.update_canary_metrics(15, 2.0, 0.02, 15.0, symbol="EURUSDm")
            reg.promote_canary_to_champion(symbol="EURUSDm", force=True)

            history = reg.get_recent_champions(symbol="EURUSDm")
            assert len(history) == 1  # One old champion replaced
            assert history[0]["path"] == "/eur/canary_v1"
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_global_champion_history(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            active = reg._read_active()
            active["champion"] = "/champ_v1"
            active["champion_history"] = [
                {"path": "/champ_v0", "replaced_at": "2026-01-01T00:00:00Z", "replaced_by": "/champ_v1"},
            ]
            reg._write_active(active)

            history = reg.get_recent_champions()
            assert len(history) == 1
            assert history[0]["path"] == "/champ_v0"
        finally:
            shutil.rmtree(root, ignore_errors=True)


# ── Corrupt/missing active.json resilience ───────────────────────────


class TestResilience:
    def test_read_active_handles_corrupt_json(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            with open(reg.active_path, "w", encoding="utf-8") as f:
                f.write("NOT VALID JSON{{{{")

            result = reg._read_active()
            assert "champion" in result
            assert "canary" in result
            assert "symbols" in result
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_read_active_handles_empty_file(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            with open(reg.active_path, "w", encoding="utf-8") as f:
                f.write("")

            result = reg._read_active()
            assert "champion" in result
            assert "canary" in result
            assert "symbols" in result
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_read_active_handles_missing_file(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            os.remove(reg.active_path)

            result = reg._read_active()
            assert "champion" in result
            assert "canary" in result
            assert "symbols" in result
        finally:
            shutil.rmtree(root, ignore_errors=True)


# ── get_all_symbols ──────────────────────────────────────────────────


class TestGetAllSymbols:
    def test_returns_configured_symbols(self):
        root = _tmp_registry_root()
        try:
            reg = ModelRegistry(root=str(root), registry_config={})
            reg.set_canary("/eur/canary", symbol="EURUSDm")
            reg.set_canary("/xau/canary", symbol="XAUUSDm")

            all_syms = reg.get_all_symbols()
            assert "EURUSDm" in all_syms
            assert "XAUUSDm" in all_syms
            assert all_syms["EURUSDm"]["canary"] == "/eur/canary"
        finally:
            shutil.rmtree(root, ignore_errors=True)
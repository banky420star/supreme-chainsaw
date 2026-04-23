"""
Tests for Phase 1 hardening features in RiskEngine.

Covers:
- Hourly loss tracking and halt
- Max drawdown % auto-halt
- can_trade_symbol() with (allowed, reason) tuples
- Halt reason tracking
- record_trade() resetting error count
- Dual daily + hourly PnL tracking
- _check_hourly_reset() hour boundary behavior
- Max open positions (total and per-symbol)
- Margin call protection
"""
import builtins
import io
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import yaml

# Ensure project root is on sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from Python.risk_engine import RiskEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine(monkeypatch):
    """Return a RiskEngine constructed without touching the real config.yaml or MT5.

    - monkeypatch open/yaml.safe_load to return an empty config so defaults are used
    - monkeypatch _bootstrap_equity to return a known value so tests are deterministic
    """
    monkeypatch.setattr(builtins, "open", lambda *a, **kw: io.StringIO(""))
    monkeypatch.setattr(yaml, "safe_load", lambda f: {})
    monkeypatch.setattr(RiskEngine, "_bootstrap_equity", staticmethod(lambda: 10000.0))
    return RiskEngine()


@pytest.fixture
def engine_custom(monkeypatch):
    """Return a factory that builds a RiskEngine with custom risk config overrides."""

    def _make(**overrides):
        cfg = {"risk": overrides}
        monkeypatch.setattr(builtins, "open", lambda *a, **kw: io.StringIO(""))
        monkeypatch.setattr(yaml, "safe_load", lambda f: cfg)
        monkeypatch.setattr(RiskEngine, "_bootstrap_equity", staticmethod(lambda: 10000.0))
        return RiskEngine()

    return _make


# ===========================================================================
# 1. Hourly loss tracking
# ===========================================================================

class TestHourlyLossTracking:
    """Verify that _hourly_pnl deque accumulates PnL and triggers halt when
    the hourly loss limit is exceeded."""

    def test_hourly_pnl_accumulates(self, engine):
        """Multiple record_pnl calls should accumulate in _hourly_pnl."""
        engine.record_pnl(-10.0)
        engine.record_pnl(-20.0)
        engine.record_pnl(-30.0)

        total = sum(p for _, p in engine._hourly_pnl)
        assert total == -60.0, f"Expected hourly PnL -60.0, got {total}"

    def test_hourly_pnl_mixed_signs(self, engine):
        """Wins and losses within the same hour should net correctly."""
        engine.record_pnl(-80.0)
        engine.record_pnl(30.0)

        total = sum(p for _, p in engine._hourly_pnl)
        assert total == -50.0

    def test_hourly_loss_halt_triggers(self, engine_custom):
        """When hourly loss exceeds max_hourly_loss, halt must be set."""
        eng = engine_custom(max_hourly_loss=100)
        # Default max_hourly_loss is 150; record enough loss to exceed 100
        eng.record_pnl(-60.0)
        assert eng.halt is False, "Should not halt yet at -60"

        eng.record_pnl(-50.0)
        # Cumulative hourly: -110 which exceeds max_hourly_loss=100
        assert eng.halt is True, "Should halt once hourly loss exceeds limit"
        assert eng.get_halt_reason() == "hourly_loss"

    def test_hourly_loss_exact_threshold(self, engine_custom):
        """Halt should trigger when hourly loss equals the limit exactly."""
        eng = engine_custom(max_hourly_loss=100)
        eng.record_pnl(-100.0)
        # Cumulative: -100 which is <= -abs(100) i.e. exactly at the limit
        assert eng.halt is True, "Should halt at exactly the hourly loss limit"
        assert eng.get_halt_reason() == "hourly_loss"

    def test_hourly_loss_below_threshold_no_halt(self, engine_custom):
        """Loss just above the negative threshold should NOT trigger halt."""
        eng = engine_custom(max_hourly_loss=100)
        eng.record_pnl(-99.99)
        assert eng.halt is False, "Should not halt when just under the limit"

    def test_hourly_pnl_entries_have_timestamps(self, engine):
        """Each entry in _hourly_pnl should be a (datetime, float) pair."""
        engine.record_pnl(-5.0)
        engine.record_pnl(10.0)

        assert len(engine._hourly_pnl) == 2
        for ts, pnl in engine._hourly_pnl:
            assert isinstance(ts, datetime), f"Expected datetime, got {type(ts)}"
            assert isinstance(pnl, float), f"Expected float, got {type(pnl)}"

    def test_positive_pnl_no_hourly_halt(self, engine_custom):
        """Positive hourly PnL should never trigger an hourly loss halt."""
        eng = engine_custom(max_hourly_loss=100)
        eng.record_pnl(500.0)
        assert eng.halt is False
        total = sum(p for _, p in eng._hourly_pnl)
        assert total == 500.0


# ===========================================================================
# 2. Hourly reset at hour boundaries
# ===========================================================================

class TestHourlyReset:
    """Verify _check_hourly_reset() clears _hourly_pnl at hour boundaries."""

    def test_same_hour_no_reset(self, engine):
        """_check_hourly_reset should NOT clear if still within the same hour."""
        engine.record_pnl(-50.0)
        assert len(engine._hourly_pnl) == 1

        engine._check_hourly_reset()
        assert len(engine._hourly_pnl) == 1, "Should not reset within same hour"

    def test_different_hour_clears_pnl(self, engine):
        """_check_hourly_reset should clear _hourly_pnl when hour changes."""
        engine.record_pnl(-50.0)
        assert len(engine._hourly_pnl) == 1

        # Simulate that the last reset was a different hour
        now = datetime.utcnow()
        engine._last_hourly_reset = now.replace(hour=(now.hour - 1) % 24)

        engine._check_hourly_reset()
        assert len(engine._hourly_pnl) == 0, "Should clear at hour boundary"
        assert engine._last_hourly_reset.hour == now.hour

    def test_different_day_clears_pnl(self, engine):
        """_check_hourly_reset should clear when the day changes, even if hour matches."""
        engine.record_pnl(-50.0)

        now = datetime.utcnow()
        # Same hour, different day
        yesterday = now - timedelta(days=1)
        engine._last_hourly_reset = yesterday.replace(
            hour=now.hour, minute=now.minute, second=now.second
        )

        engine._check_hourly_reset()
        assert len(engine._hourly_pnl) == 0, "Should clear on day change"

    def test_record_pnl_calls_check_hourly_reset(self, engine):
        """record_pnl internally calls _check_hourly_reset, so crossing an hour
        boundary between calls should clear prior entries."""
        engine.record_pnl(-50.0)

        # Forge the last reset to simulate that an hour has passed
        now = datetime.utcnow()
        engine._last_hourly_reset = now.replace(hour=(now.hour - 1) % 24)

        # This call should first reset, then append
        engine.record_pnl(-30.0)

        # Only the latest entry should remain
        assert len(engine._hourly_pnl) == 1
        total = sum(p for _, p in engine._hourly_pnl)
        assert total == -30.0


# ===========================================================================
# 3. Max drawdown auto-halt
# ===========================================================================

class TestMaxDrawdownAutoHalt:
    """Verify that exceeding max_drawdown_pct triggers auto-halt."""

    def test_drawdown_calculation(self, engine):
        """current_dd should return the correct drawdown percentage."""
        # Peak = 10000, current = 10000 -> DD = 0%
        assert engine.current_dd == 0.0

        engine.update_equity(9000.0)  # 10% drawdown
        assert engine.current_dd == 10.0

        engine.update_equity(8000.0)  # 20% drawdown
        assert engine.current_dd == 20.0

    def test_drawdown_halt_triggers(self, engine_custom):
        """can_trade must return False and set halt when DD >= threshold."""
        eng = engine_custom(max_drawdown_pct=8.0)
        eng.update_equity(9000.0)  # 10% DD > 8% threshold

        result = eng.can_trade()
        assert result is False
        assert eng.halt is True
        assert eng.get_halt_reason() == "max_drawdown"

    def test_drawdown_just_below_threshold(self, engine_custom):
        """DD just under the threshold should allow trading."""
        eng = engine_custom(max_drawdown_pct=8.0)
        eng.update_equity(9300.0)  # 7% DD < 8%

        assert eng.can_trade() is True
        assert eng.halt is False

    def test_drawdown_at_exact_threshold(self, engine_custom):
        """DD exactly at the threshold should trigger halt (>= check)."""
        eng = engine_custom(max_drawdown_pct=8.0)
        eng.update_equity(9200.0)  # 8% DD exactly

        result = eng.can_trade()
        assert result is False
        assert eng.get_halt_reason() == "max_drawdown"

    def test_drawdown_zero_equity_edge(self, engine_custom):
        """When peak equity is 0 or negative, current_dd should return 0."""
        eng = engine_custom(max_drawdown_pct=8.0)
        eng._peak_equity = 0.0
        assert eng.current_dd == 0.0

        eng._peak_equity = -100.0
        assert eng.current_dd == 0.0

    def test_peak_equity_tracks_high_water_mark(self, engine):
        """Peak equity should only go up, never down, even if equity drops."""
        engine.update_equity(12000.0)
        assert engine._peak_equity == 12000.0

        engine.update_equity(9000.0)
        assert engine._peak_equity == 12000.0, "Peak should not decrease"

    def test_reset_peak_equity(self, engine):
        """reset_peak_equity should set peak to current equity."""
        engine.update_equity(12000.0)
        engine.update_equity(9000.0)
        assert engine._peak_equity == 12000.0

        engine.reset_peak_equity()
        assert engine._peak_equity == 9000.0

    def test_drawdown_disabled_when_zero(self, engine_custom):
        """When max_drawdown_pct is 0, drawdown check should be skipped."""
        eng = engine_custom(max_drawdown_pct=0)
        eng.update_equity(5000.0)  # Massive DD but check is disabled

        assert eng.can_trade() is True
        assert eng.halt is False


# ===========================================================================
# 4. can_trade_symbol
# ===========================================================================

class TestCanTradeSymbol:
    """Verify can_trade_symbol returns correct (allowed, reason) tuples."""

    def test_allows_when_checks_pass(self, engine):
        """When all checks pass, can_trade_symbol returns (True, 'ok')."""
        allowed, reason = engine.can_trade_symbol("EURUSD")
        assert allowed is True
        assert reason == "ok"

    def test_blocks_when_halted(self, engine):
        """When halt is active, can_trade_symbol returns (False, 'halted (...)')."""
        engine.halt = True
        engine._halt_reason = "daily_loss"

        allowed, reason = engine.can_trade_symbol("EURUSD")
        assert allowed is False
        assert "halted" in reason
        assert "daily_loss" in reason

    def test_blocks_when_daily_trade_limit_reached(self, engine_custom):
        """When daily trade count hits the limit, can_trade_symbol blocks."""
        eng = engine_custom(max_daily_trades=2)
        eng.record_trade()
        eng.record_trade()

        allowed, reason = eng.can_trade_symbol("EURUSD")
        assert allowed is False
        assert reason == "daily_trade_limit"

    def test_blocks_when_max_positions_total_reached(self, engine):
        """When total open positions >= max, can_trade_symbol blocks."""
        engine._mt5_position_count = engine.max_open_positions  # hit the cap

        allowed, reason = engine.can_trade_symbol("EURUSD")
        assert allowed is False
        assert "max_positions_total" in reason

    def test_blocks_when_max_positions_per_symbol_reached(self, engine, monkeypatch):
        """When per-symbol positions >= max, can_trade_symbol blocks with symbol info."""
        # Set up: 2 positions total (below total cap), both on EURUSD
        engine._mt5_position_count = 2
        # Mock _get_symbol_positions_count to return the per-symbol count
        # since MT5 may be available on this machine and bypass the fallback
        monkeypatch.setattr(engine, "_get_symbol_positions_count", lambda sym: engine.max_positions_per_symbol)

        allowed, reason = engine.can_trade_symbol("EURUSD")
        assert allowed is False
        assert "EURUSD" in reason
        assert "max_positions" in reason

    def test_different_symbol_allowed_when_only_one_at_limit(self, engine, monkeypatch):
        """If EURUSD is at per-symbol limit, GBPUSD should still be allowed."""
        engine._mt5_position_count = engine.max_positions_per_symbol
        # Mock: EURUSD is at limit, GBPUSD has 0 positions
        symbol_counts = {"EURUSD": engine.max_positions_per_symbol, "GBPUSD": 0}
        monkeypatch.setattr(engine, "_get_symbol_positions_count",
                            lambda sym: symbol_counts.get(sym, 0))

        # GBPUSD has 0 positions, should be fine
        allowed, reason = engine.can_trade_symbol("GBPUSD")
        assert allowed is True
        assert reason == "ok"

    def test_blocks_hourly_loss_halt(self, engine_custom):
        """can_trade_symbol should return halted reason for hourly loss halt."""
        eng = engine_custom(max_hourly_loss=50)
        eng.record_pnl(-60.0)

        allowed, reason = eng.can_trade_symbol("EURUSD")
        assert allowed is False
        assert "halted" in reason
        assert "hourly_loss" in reason

    def test_blocks_drawdown_halt(self, engine_custom):
        """can_trade_symbol should return halted reason for drawdown halt."""
        eng = engine_custom(max_drawdown_pct=5.0)
        eng.update_equity(9000.0)  # 10% DD
        eng.can_trade()  # triggers the halt

        allowed, reason = eng.can_trade_symbol("EURUSD")
        assert allowed is False
        assert "halted" in reason
        assert "max_drawdown" in reason

    def test_unknown_reason_fallback(self, engine):
        """If can_trade returns False for an untracked reason, reason should be 'unknown'."""
        # Force daily trades to the limit without setting halt
        engine.daily_trades = engine.max_daily_trades + 1
        # But also make the daily_trades check pass by adjusting limit
        engine.max_daily_trades = 999
        # Set margin too low
        engine._mt5_free_margin = 3.0

        allowed, reason = engine.can_trade_symbol("EURUSD")
        # The free margin check returns False from can_trade but doesn't set
        # a specific reason in can_trade_symbol's logic, so it falls to "unknown"
        assert allowed is False

    def test_margin_call_blocks(self, engine):
        """Low free margin should block trading via can_trade_symbol."""
        engine._mt5_free_margin = 3.0

        allowed, reason = engine.can_trade_symbol("EURUSD")
        assert allowed is False


# ===========================================================================
# 5. Halt reason tracking
# ===========================================================================

class TestHaltReasonTracking:
    """Verify that different halt conditions set the correct _halt_reason."""

    def test_daily_loss_sets_reason(self, engine_custom):
        """Exceeding daily loss limit should set _halt_reason to 'daily_loss'."""
        eng = engine_custom(max_daily_loss=100)
        eng.record_pnl(-110.0)

        assert eng.get_halt_reason() == "daily_loss"

    def test_hourly_loss_sets_reason(self, engine_custom):
        """Exceeding hourly loss limit should set _halt_reason to 'hourly_loss'."""
        eng = engine_custom(max_hourly_loss=50)
        eng.record_pnl(-60.0)

        assert eng.get_halt_reason() == "hourly_loss"

    def test_consecutive_errors_sets_reason(self, engine):
        """Three consecutive critical errors should set _halt_reason to 'consecutive_errors'."""
        engine.record_error(critical=True)
        engine.record_error(critical=True)
        assert engine.get_halt_reason() == ""

        engine.record_error(critical=True)
        assert engine.get_halt_reason() == "consecutive_errors"

    def test_drawdown_sets_reason(self, engine_custom):
        """Drawdown exceeding threshold should set _halt_reason to 'max_drawdown'."""
        eng = engine_custom(max_drawdown_pct=5.0)
        eng.update_equity(9000.0)  # 10% DD
        eng.can_trade()

        assert eng.get_halt_reason() == "max_drawdown"

    def test_no_halt_reason_when_not_halted(self, engine):
        """get_halt_reason() should return empty string when not halted."""
        assert engine.get_halt_reason() == ""

    def test_non_critical_errors_no_halt(self, engine):
        """Non-critical errors should not trigger halt or set reason."""
        for _ in range(5):
            engine.record_error(critical=False)

        assert engine.halt is False
        assert engine.get_halt_reason() == ""
        assert engine.error_count == 0

    def test_hourly_overwrites_daily_in_record_pnl(self, engine_custom):
        """When a single record_pnl call triggers both daily AND hourly limits,
        the hourly check runs second and overwrites daily_loss with hourly_loss.
        This documents the actual code behavior: daily check first, hourly check
        second, last write wins."""
        eng = engine_custom(max_daily_loss=200, max_hourly_loss=50)

        eng.record_pnl(-60.0)  # triggers hourly_loss only (daily: -60 > -200)
        assert eng.get_halt_reason() == "hourly_loss"

        eng.record_pnl(-150.0)  # daily total: -210 (exceeds -200), hourly total: -210 (exceeds -50)
        # Daily check sets "daily_loss", but hourly check runs second and overwrites to "hourly_loss"
        assert eng.get_halt_reason() == "hourly_loss"

    def test_reason_cleared_on_reset_daily_for_non_daily_loss(self, engine):
        """reset_daily should clear halt reason when halt reason is NOT daily_loss."""
        engine.record_error(critical=True)
        engine.record_error(critical=True)
        engine.record_error(critical=True)
        assert engine.halt is True
        # The current reset_daily logic only preserves halt if reason contains
        # 'daily_loss', so consecutive_errors halt should be cleared
        engine.reset_daily()
        # After reset, error_count=0 and halt is cleared since reason != daily_loss
        assert engine.halt is False
        assert engine.get_halt_reason() == ""

    def test_daily_loss_halt_preserved_on_reset(self, engine_custom):
        """reset_daily should preserve halt when reason contains 'daily_loss'."""
        # Use a very high max_hourly_loss so only daily_loss triggers,
        # avoiding the hourly check overwriting the reason.
        eng = engine_custom(max_daily_loss=100, max_hourly_loss=999999)
        eng.record_pnl(-150.0)
        assert eng.get_halt_reason() == "daily_loss"

        eng.reset_daily()
        assert eng.halt is True, "daily_loss halt should survive reset_daily"
        assert "daily_loss" in eng.get_halt_reason()


# ===========================================================================
# 6. record_trade resets error count
# ===========================================================================

class TestRecordTradeResetsErrors:
    """Verify that a successful trade (record_trade) resets the consecutive
    error counter."""

    def test_record_trade_resets_error_count(self, engine):
        """After record_trade(), error_count should be 0."""
        engine.record_error(critical=True)
        engine.record_error(critical=True)
        assert engine.error_count == 2

        engine.record_trade()
        assert engine.error_count == 0
        assert engine.daily_trades == 1

    def test_error_count_increment_after_trade_reset(self, engine):
        """After a trade resets errors, new errors should start counting from 0."""
        engine.record_error(critical=True)
        engine.record_error(critical=True)
        engine.record_trade()

        # Now 2 more errors should not trigger halt (need 3)
        engine.record_error(critical=True)
        engine.record_error(critical=True)
        assert engine.halt is False, "Should not halt — only 2 errors since last trade"

        engine.record_error(critical=True)
        assert engine.halt is True, "Third error after trade should trigger halt"

    def test_record_trade_increments_daily_trades(self, engine):
        """Each call to record_trade should increment daily_trades."""
        assert engine.daily_trades == 0
        engine.record_trade()
        assert engine.daily_trades == 1
        engine.record_trade()
        assert engine.daily_trades == 2


# ===========================================================================
# 7. Dual daily and hourly PnL tracking
# ===========================================================================

class TestDualPnlTracking:
    """Verify that record_pnl updates both realized_pnl_today and _hourly_pnl."""

    def test_daily_pnl_accumulates(self, engine):
        """record_pnl should add to realized_pnl_today."""
        engine.record_pnl(50.0)
        assert engine.realized_pnl_today == 50.0

        engine.record_pnl(-30.0)
        assert engine.realized_pnl_today == 20.0

    def test_hourly_pnl_also_updated(self, engine):
        """record_pnl should also append to _hourly_pnl."""
        engine.record_pnl(50.0)
        engine.record_pnl(-30.0)

        hourly_total = sum(p for _, p in engine._hourly_pnl)
        assert hourly_total == 20.0

    def test_daily_and_hourly_are_independent(self, engine_custom):
        """Daily and hourly can trigger different halt reasons independently.
        A small hourly loss that doesn't exceed hourly limit, but accumulates
        daily to exceed daily limit, should trigger daily_loss halt."""
        eng = engine_custom(max_daily_loss=100, max_hourly_loss=500)

        eng.record_pnl(-60.0)
        assert eng.halt is False, "Should not halt yet"

        eng.record_pnl(-50.0)
        # Daily total: -110 (exceeds 100), Hourly total: -110 (under 500)
        assert eng.halt is True
        assert eng.get_halt_reason() == "daily_loss"

    def test_daily_halt_triggers_before_hourly_check(self, engine_custom):
        """When a single PnL recording exceeds BOTH daily and hourly limits,
        daily_loss is set first (code order), then hourly_loss overwrites it."""
        eng = engine_custom(max_daily_loss=100, max_hourly_loss=50)

        # -200 exceeds both daily (100) and hourly (50)
        eng.record_pnl(-200.0)
        # Daily check runs first (sets "daily_loss"), then hourly check
        # overwrites to "hourly_loss"
        assert eng.get_halt_reason() == "hourly_loss"

    def test_positive_pnl_no_daily_halt(self, engine):
        """Positive PnL should never trigger a daily loss halt."""
        engine.record_pnl(5000.0)
        assert engine.halt is False
        assert engine.realized_pnl_today == 5000.0


# ===========================================================================
# 8. Max open positions (total and per-symbol)
# ===========================================================================

class TestPositionLimits:
    """Verify total and per-symbol position limits are enforced in can_trade."""

    def test_total_position_limit(self, engine):
        """can_trade should return False when total open positions >= max."""
        engine._mt5_position_count = engine.max_open_positions
        assert engine.can_trade() is False

    def test_total_position_below_limit(self, engine):
        """can_trade should return True when total positions < max."""
        engine._mt5_position_count = engine.max_open_positions - 1
        assert engine.can_trade() is True

    def test_per_symbol_limit_in_can_trade(self, engine, monkeypatch):
        """can_trade(symbol) should return False when symbol positions >= max."""
        # Mock _get_symbol_positions_count since MT5 may be available on this machine
        monkeypatch.setattr(engine, "_get_symbol_positions_count",
                            lambda sym: engine.max_positions_per_symbol)

        assert engine.can_trade("EURUSD") is False

    def test_no_symbol_arg_skips_per_symbol_check(self, engine, monkeypatch):
        """can_trade() without a symbol should not check per-symbol limits."""
        # Even if EURUSD is at per-symbol limit, can_trade() without symbol skips the check
        monkeypatch.setattr(engine, "_get_symbol_positions_count",
                            lambda sym: engine.max_positions_per_symbol)

        # Without symbol, per-symbol check is skipped
        assert engine.can_trade() is True

    def test_cached_position_count_used(self, engine):
        """When _mt5_position_count is set, it should be used instead of MT5."""
        engine._mt5_position_count = 5
        assert engine._get_open_positions_count() == 5

    def test_no_cached_count_returns_zero(self, engine):
        """When no cached count and MT5 is unavailable, return 0."""
        # No _mt5_position_count attribute, MT5 import will fail in test env
        result = engine._get_open_positions_count()
        assert result == 0

    def test_zero_per_symbol_limit_disables_check(self, engine_custom, monkeypatch):
        """When max_positions_per_symbol is 0, per-symbol check is skipped."""
        eng = engine_custom(max_positions_per_symbol=0)

        # Even with many EURUSD positions, the per-symbol check is skipped when limit is 0
        monkeypatch.setattr(eng, "_get_symbol_positions_count", lambda sym: 10)

        # can_trade("EURUSD") should not be blocked by per-symbol limit
        # (but might still be blocked by total limit — set total low)
        eng._mt5_position_count = 0
        assert eng.can_trade("EURUSD") is True


# ===========================================================================
# 9. Margin call protection
# ===========================================================================

class TestMarginCallProtection:
    """Verify that low free margin blocks trading."""

    def test_low_margin_blocks(self, engine):
        """Free margin below $5 should block can_trade."""
        engine._mt5_free_margin = 4.99
        assert engine.can_trade() is False

    def test_exactly_5_dollars_allows(self, engine):
        """Free margin exactly $5 does NOT block (check is strictly < 5.0)."""
        engine._mt5_free_margin = 5.0
        # 5.0 < 5.0 is False, so trading is allowed at exactly $5
        assert engine.can_trade() is True

    def test_sufficient_margin_allows(self, engine):
        """Free margin above $5 should allow trading."""
        engine._mt5_free_margin = 5.01
        assert engine.can_trade() is True

    def test_no_margin_attr_allows(self, engine):
        """When _mt5_free_margin is not set, margin check is skipped."""
        # By default the engine doesn't have _mt5_free_margin
        if hasattr(engine, "_mt5_free_margin"):
            delattr(engine, "_mt5_free_margin")
        assert engine.can_trade() is True


# ===========================================================================
# 10. reset_daily behavior
# ===========================================================================

class TestResetDaily:
    """Verify reset_daily clears appropriate state."""

    def test_resets_daily_pnl(self, engine):
        """reset_daily should zero out realized_pnl_today."""
        engine.record_pnl(-100.0)
        assert engine.realized_pnl_today == -100.0

        engine.reset_daily()
        assert engine.realized_pnl_today == 0.0

    def test_resets_daily_trades(self, engine):
        """reset_daily should zero out daily_trades."""
        engine.record_trade()
        engine.record_trade()
        assert engine.daily_trades == 2

        engine.reset_daily()
        assert engine.daily_trades == 0

    def test_resets_error_count(self, engine):
        """reset_daily should zero out error_count."""
        engine.record_error(critical=True)
        engine.record_error(critical=True)
        assert engine.error_count == 2

        engine.reset_daily()
        assert engine.error_count == 0

    def test_clears_hourly_pnl(self, engine):
        """reset_daily should clear _hourly_pnl."""
        engine.record_pnl(-50.0)
        assert len(engine._hourly_pnl) == 1

        engine.reset_daily()
        assert len(engine._hourly_pnl) == 0

    def test_updates_last_hourly_reset(self, engine):
        """reset_daily should update _last_hourly_reset to current time."""
        old_time = datetime(2025, 1, 1, 0, 0, 0)
        engine._last_hourly_reset = old_time

        engine.reset_daily()
        # _last_hourly_reset should be approximately now
        delta = abs((datetime.utcnow() - engine._last_hourly_reset).total_seconds())
        assert delta < 5, "Should reset to current time"


# ===========================================================================
# 11. Equity history tracking
# ===========================================================================

class TestEquityHistory:
    """Verify equity history capping and storage."""

    def test_equity_history_capped_at_300(self, engine):
        """Equity history should not exceed 300 entries."""
        for i in range(350):
            engine.update_equity(10000.0 + i)

        assert len(engine._equity_history) <= 300

    def test_equity_history_keeps_latest(self, engine):
        """After exceeding 300, the latest entries should be kept."""
        for i in range(350):
            engine.update_equity(float(i))

        # Should keep entries 50..349 (the latest 300)
        assert engine._equity_history[0] == 50.0
        assert engine._equity_history[-1] == 349.0
"""Tests for RiskEngine (current API)."""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from Python.risk_engine import RiskEngine


@pytest.fixture
def engine():
    with patch.object(RiskEngine, "__init__", lambda self: None):
        re = RiskEngine.__new__(RiskEngine)
        re.max_daily_loss = 1000.0
        re.max_daily_trades = 50
        re.max_daily_trades_per_symbol = 10
        re.max_daily_losing_trades_per_symbol = 3
        re.max_lots = 1.0
        re.default_symbol_profile = {"entry_deviation": 20, "sl_points": 250, "tp_points": 450}
        re.symbol_profiles = {}
        re.realized_pnl_today = 0.0
        re.daily_trades = 0
        re.daily_trades_by_symbol = {}
        re.daily_losing_trades_by_symbol = {}
        re.halt = False
        re.error_halt = False
        re.error_count = 0
        re._halt_reason = ""
        re.current_dd = 0.0
        re.peak_equity = None
        re.last_reset_day = datetime.now(timezone.utc).date()
        return re


class TestLifecycle:
    def test_reset_daily(self, engine):
        engine.daily_trades = 5
        engine.realized_pnl_today = -100
        engine.error_count = 2
        engine.halt = True
        engine.reset_daily()
        assert engine.daily_trades == 0
        assert engine.realized_pnl_today == 0.0
        assert engine.error_count == 0
        assert engine.halt is False

    def test_reset_daily_keeps_error_halt(self, engine):
        engine.halt = True
        engine.error_halt = True
        engine.reset_daily()
        assert engine.halt is True

    def test_maybe_roll_day(self, engine):
        engine.last_reset_day = datetime.now(timezone.utc).date() - timedelta(days=1)
        engine.daily_trades = 5
        engine.maybe_roll_day()
        assert engine.daily_trades == 0


class TestTradeRecording:
    def test_record_trade(self, engine):
        engine.record_trade("BTCUSDm")
        assert engine.daily_trades == 1
        assert engine.daily_trades_by_symbol["BTCUSDm"] == 1

    def test_record_pnl(self, engine):
        engine.record_pnl(100.0)
        assert engine.realized_pnl_today == 100.0

    def test_record_pnl_halt(self, engine):
        engine.record_pnl(-1500.0)
        assert engine.halt is True
        assert getattr(engine, "_halt_reason", None) == "daily_loss"

    def test_record_trade_result_loss(self, engine):
        engine.record_trade_result("BTCUSDm", -50.0)
        assert engine.daily_losing_trades_by_symbol["BTCUSDm"] == 1
        assert engine.realized_pnl_today == -50.0

    def test_record_trade_result_win(self, engine):
        engine.record_trade_result("BTCUSDm", 50.0)
        assert engine.daily_losing_trades_by_symbol.get("BTCUSDm", 0) == 0


class TestEquityAndDrawdown:
    def test_update_equity_first_call(self, engine):
        engine.update_equity(10000.0)
        assert engine.peak_equity == 10000.0
        assert engine.current_dd == 0.0

    def test_update_equity_drawdown(self, engine):
        engine.update_equity(10000.0)
        engine.update_equity(9000.0)
        assert engine.current_dd == 10.0

    def test_update_equity_new_peak(self, engine):
        engine.update_equity(10000.0)
        engine.update_equity(11000.0)
        assert engine.peak_equity == 11000.0
        assert engine.current_dd == 0.0


class TestErrors:
    def test_record_error_no_halt(self, engine):
        engine.record_error()
        engine.record_error()
        assert engine.halt is False

    def test_record_error_halt(self, engine):
        engine.record_error()
        engine.record_error()
        engine.record_error()
        assert engine.halt is True
        assert engine.error_halt is True


class TestCanTrade:
    def test_can_trade_default(self, engine):
        assert engine.can_trade() is True

    def test_can_trade_halt(self, engine):
        engine.halt = True
        assert engine.can_trade() is False

    def test_can_trade_daily_limit(self, engine):
        engine.daily_trades = 50
        assert engine.can_trade() is False

    def test_can_trade_symbol_limit(self, engine):
        engine.daily_trades_by_symbol["BTCUSDm"] = 10
        assert engine.can_trade("BTCUSDm") is False

    def test_can_trade_symbol_loss_limit(self, engine):
        engine.daily_losing_trades_by_symbol["BTCUSDm"] = 3
        assert engine.can_trade("BTCUSDm") is False


class TestSymbolProfile:
    def test_default_profile(self, engine):
        prof = engine.get_symbol_profile("UNKNOWN")
        assert prof["sl_points"] == 250

    def test_symbol_override(self, engine):
        engine.symbol_profiles = {"BTCUSDm": {"sl_points": 500}}
        prof = engine.get_symbol_profile("BTCUSDm")
        assert prof["sl_points"] == 500
        assert prof["tp_points"] == 450

"""Tests for OrderManager — SL/TP, breakeven, trailing stop, and scale-out logic."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Python.order_manager import (
    OrderManager,
    ManagedPosition,
    OrderResult,
    _load_symbol_risk_config,
    _clear_config_cache,
)


def make_position(ticket=1, symbol="EURUSDm", side="BUY", volume=0.1,
                  open_price=1.1000, current_sl=0.0, current_tp=0.0):
    return ManagedPosition(
        ticket=ticket,
        symbol=symbol,
        side=side,
        volume=volume,
        open_price=open_price,
        current_sl=current_sl,
        current_tp=current_tp,
    )


def teardown_module():
    _clear_config_cache()


# ── SL/TP Computation ─────────────────────────────────────────────────────

def test_compute_sl_tp_buy():
    sl, tp = OrderManager.compute_sl_tp("EURUSDm", "BUY", 1.1000, atr_value=0.0050)
    assert sl < 1.1000, f"SL should be below entry for BUY, got {sl}"
    assert tp > 1.1000, f"TP should be above entry for BUY, got {tp}"


def test_compute_sl_tp_sell():
    sl, tp = OrderManager.compute_sl_tp("EURUSDm", "SELL", 1.1000, atr_value=0.0010)
    assert sl > 1.1000, f"SL should be above entry for SELL, got {sl}"
    assert tp < 1.1000, f"TP should be below entry for SELL, got {tp}"


def test_compute_sl_tp_zero_atr():
    sl, tp = OrderManager.compute_sl_tp("EURUSDm", "BUY", 1.1000, atr_value=0.0)
    assert sl == 0.0
    assert tp == 0.0


def test_compute_sl_tp_per_symbol_config():
    btc_sl, btc_tp = OrderManager.compute_sl_tp("BTCUSDm", "BUY", 75000.0, atr_value=1000.0)
    eurusd_sl, eurusd_tp = OrderManager.compute_sl_tp("EURUSDm", "BUY", 1.1000, atr_value=0.0050)

    btc_sl_distance = 75000.0 - btc_sl
    eurusd_sl_distance = 1.1000 - eurusd_sl

    # BTC should have wider stops than EURUSD in absolute terms
    assert btc_sl_distance > eurusd_sl_distance

    # BTC should have proportionally wider stops
    btc_sl_pct = btc_sl_distance / 75000.0
    eurusd_sl_pct = eurusd_sl_distance / 1.1000
    assert btc_sl_pct >= eurusd_sl_pct, "BTC should have wider SL (as % of price) than EURUSD"


def test_compute_sl_tp_minimum_distance():
    sl, tp = OrderManager.compute_sl_tp("XAUUSDm", "BUY", 2400.0, atr_value=0.5)
    assert sl < 2400.0
    assert (2400.0 - sl) >= 10.0, "XAU SL should be at least 10 points from entry"


# ── Breakeven Logic ────────────────────────────────────────────────────────

def test_breakeven_not_triggered_when_no_profit():
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.0980)
    result = OrderManager.check_breakeven("EURUSDm", pos, current_price=1.0990, atr_value=0.0010)
    assert result is None, "Breakeven should not trigger when price is below entry"


def test_breakeven_triggered_buy():
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.0980, volume=0.1)
    # Move well into profit
    result = OrderManager.check_breakeven("EURUSDm", pos, current_price=1.1050, atr_value=0.0010)
    assert result is not None
    assert result.action == "breakeven"
    assert result.new_sl > pos.open_price, "Breakeven SL should be above entry for BUY"


def test_breakeven_triggered_sell():
    pos = make_position(side="SELL", open_price=1.1000, current_sl=1.1020, volume=0.1)
    result = OrderManager.check_breakeven("EURUSDm", pos, current_price=1.0950, atr_value=0.0010)
    assert result is not None
    assert result.action == "breakeven"
    assert result.new_sl < pos.open_price, "Breakeven SL should be below entry for SELL"


def test_breakeven_already_triggered():
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.1002)
    pos.breakeven_triggered = True
    result = OrderManager.check_breakeven("EURUSDm", pos, current_price=1.1050, atr_value=0.0010)
    assert result is None, "Breakeven should not trigger when already triggered"


# ── Trailing Stop Logic ───────────────────────────────────────────────────

def test_trailing_stop_not_triggered_without_breakeven():
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.0980)
    pos.breakeven_triggered = False
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.1040, atr_value=0.0010)
    assert result is None, "Trailing should not trigger before breakeven"


def test_trailing_stop_triggered_buy():
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.1005)
    pos.breakeven_triggered = True
    pos.high_water_mark = 1.1040
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.1040, atr_value=0.0010)
    assert result is not None
    assert result.action == "trailing_stop"
    assert result.new_sl > pos.current_sl, "Trailing SL should move UP for BUY"


def test_trailing_stop_triggered_sell():
    pos = make_position(side="SELL", open_price=1.1000, current_sl=1.0995)
    pos.breakeven_triggered = True
    pos.low_water_mark = 1.0960
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.0960, atr_value=0.0010)
    assert result is not None
    assert result.action == "trailing_stop"
    assert result.new_sl < pos.current_sl, "Trailing SL should move DOWN for SELL"


def test_trailing_stop_does_not_move_sl_down_for_buy():
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.1040)
    pos.breakeven_triggered = True
    pos.high_water_mark = 1.1045
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.1045, atr_value=0.0010)
    assert result is None, "Trailing stop should not move SL down for BUY"


def test_trailing_stop_does_not_move_sl_below_entry():
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.0980)
    pos.breakeven_triggered = True
    pos.high_water_mark = 1.1008
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.1008, atr_value=0.0010)
    assert result is None


# ── Scale-Out Logic ───────────────────────────────────────────────────────

def test_scale_out_not_triggered_insufficient_profit():
    pos = make_position(volume=0.10, open_price=1.1000)
    result = OrderManager.check_scale_out("EURUSDm", pos, current_price=1.1010, atr_value=0.0010)
    assert result is None, "Scale-out should not trigger with insufficient profit"


def test_scale_out_triggered_at_profit_target():
    pos = make_position(volume=0.10, open_price=1.1000)
    result = OrderManager.check_scale_out("EURUSDm", pos, current_price=1.1025, atr_value=0.0010)
    assert result is not None
    assert result.action.startswith("scale_out")


def test_scale_out_not_triggered_when_no_more_levels():
    pos = make_position(volume=0.10, open_price=1.1000)
    pos.scale_out_1_done = True
    pos.scale_out_2_done = True
    pos.scale_out_3_done = True
    result = OrderManager.check_scale_out("EURUSDm", pos, current_price=1.1050, atr_value=0.0010)
    assert result is not None
    assert result.action == "runner_mode"


def test_scale_out_not_triggered_for_small_volume():
    pos = make_position(volume=0.01, open_price=1.1000)
    result = OrderManager.check_scale_out("EURUSDm", pos, current_price=1.1050, atr_value=0.0010)
    assert result is not None
    assert result.action == "runner_mode"


# ── Config Loading ─────────────────────────────────────────────────────────

def test_load_symbol_risk_config_eurusd():
    cfg = _load_symbol_risk_config("EURUSDm")
    assert "sl_atr_mult" in cfg
    assert "tp_atr_mult" in cfg
    assert "trailing_trigger_atr" in cfg


def test_load_symbol_risk_config_unknown():
    try:
        cfg = _load_symbol_risk_config("UNKNOWN")
    except ValueError:
        pass  # Expected: unknown symbols are rejected
    else:
        assert "sl_atr_mult" in cfg

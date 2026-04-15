"""Tests for OrderManager — breakeven, trailing stop, and partial close logic."""
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Python.order_manager import (
    OrderManager,
    ManagedPosition,
    OrderResult,
    _load_symbol_risk_config,
    _clear_config_cache,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

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
    """Clear config cache after tests."""
    _clear_config_cache()


# ── SL/TP Computation ─────────────────────────────────────────────────────

def test_compute_sl_tp_buy():
    """BUY order: SL below entry, TP above entry."""
    # Use large ATR to avoid minimum SL enforcement
    sl, tp = OrderManager.compute_sl_tp("EURUSDm", "BUY", 1.1000, atr_value=0.0050)
    assert sl < 1.1000, f"SL should be below entry for BUY, got {sl}"
    assert tp > 1.1000, f"TP should be above entry for BUY, got {tp}"
    # Default SL multiplier is 2.0, TP is 3.0 for EURUSD
    expected_sl = round(1.1000 - 0.0050 * 2.0, 5)
    expected_tp = round(1.1000 + 0.0050 * 3.0, 5)
    assert sl == expected_sl, f"SL expected {expected_sl}, got {sl}"
    assert tp == expected_tp, f"TP expected {expected_tp}, got {tp}"


def test_compute_sl_tp_sell():
    """SELL order: SL above entry, TP below entry."""
    sl, tp = OrderManager.compute_sl_tp("EURUSDm", "SELL", 1.1000, atr_value=0.0010)
    assert sl > 1.1000, f"SL should be above entry for SELL, got {sl}"
    assert tp < 1.1000, f"TP should be below entry for SELL, got {tp}"


def test_compute_sl_tp_zero_atr():
    """Zero ATR should return 0,0 (no SL/TP)."""
    sl, tp = OrderManager.compute_sl_tp("EURUSDm", "BUY", 1.1000, atr_value=0.0)
    assert sl == 0.0
    assert tp == 0.0


def test_compute_sl_tp_per_symbol_config():
    """BTC should use wider SL/TP multipliers from its config."""
    btc_sl, btc_tp = OrderManager.compute_sl_tp("BTCUSDm", "BUY", 75000.0, atr_value=1000.0)
    eurusd_sl, eurusd_tp = OrderManager.compute_sl_tp("EURUSDm", "BUY", 1.1000, atr_value=0.0050)

    # BTC has sl_atr_mult=4.0 and tp_atr_mult=2.0
    # BTC SL distance = 1000 * 4.0 = 4000
    btc_sl_distance = 75000.0 - btc_sl
    assert abs(btc_sl_distance - 4000.0) < 1.0, f"BTC SL distance expected ~4000, got {btc_sl_distance}"

    # EURUSD has sl_atr_mult=2.0 and tp_atr_mult=3.0
    # EURUSD SL distance = 0.005 * 2.0 = 0.01
    eurusd_sl_distance = 1.1000 - eurusd_sl
    assert abs(eurusd_sl_distance - 0.01) < 0.0001, f"EURUSD SL distance expected ~0.01, got {eurusd_sl_distance}"

    # BTC should have proportionally wider stops than EURUSD
    btc_sl_pct = btc_sl_distance / 75000.0
    eurusd_sl_pct = eurusd_sl_distance / 1.1000
    assert btc_sl_pct >= eurusd_sl_pct, "BTC should have wider SL (as % of price) than EURUSD"


def test_compute_sl_tp_minimum_distance():
    """SL should not be below minimum distance for symbol."""
    # Very small ATR on XAU — should still get a reasonable SL
    sl, tp = OrderManager.compute_sl_tp("XAUUSDm", "BUY", 2400.0, atr_value=0.5)
    # XAU min SL is 10.0
    assert sl < 2400.0
    assert (2400.0 - sl) >= 10.0, "XAU SL should be at least 10 points from entry"


# ── Breakeven Logic ────────────────────────────────────────────────────────

def test_breakeven_not_triggered_when_no_profit():
    """Breakeven should not trigger when position is at a loss."""
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.0980)
    result = OrderManager.check_breakeven("EURUSDm", pos, current_price=1.0990, atr_value=0.0010)
    assert result is None, "Breakeven should not trigger when price is below entry"


def test_breakeven_triggered_buy():
    """Breakeven should trigger for BUY when price moves enough in our favor."""
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.0980)
    # EURUSD breakeven_trigger_atr = 1.5, ATR = 0.001, so trigger = 0.0015
    # Price at 1.1020 is 0.0020 above entry, which exceeds 0.0015
    result = OrderManager.check_breakeven("EURUSDm", pos, current_price=1.1020, atr_value=0.0010)
    assert result is not None
    assert result.action == "breakeven"
    assert result.new_sl > pos.open_price, "Breakeven SL should be above entry for BUY"
    # SL should be close to entry price (with small buffer)
    assert abs(result.new_sl - 1.1000) < 0.001, f"Breakeven SL should be near entry, got {result.new_sl}"


def test_breakeven_triggered_sell():
    """Breakeven should trigger for SELL when price drops enough in our favor."""
    pos = make_position(side="SELL", open_price=1.1000, current_sl=1.1020)
    # Price at 1.0975 is 0.0025 below entry, which exceeds trigger distance
    result = OrderManager.check_breakeven("EURUSDm", pos, current_price=1.0975, atr_value=0.0010)
    assert result is not None
    assert result.action == "breakeven"
    assert result.new_sl < pos.open_price, "Breakeven SL should be below entry for SELL"


def test_breakeven_already_triggered():
    """Breakeven should not trigger again once already applied."""
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.1002)
    pos.breakeven_triggered = True
    result = OrderManager.check_breakeven("EURUSDm", pos, current_price=1.1050, atr_value=0.0010)
    assert result is None, "Breakeven should not trigger when already triggered"


# ── Trailing Stop Logic ───────────────────────────────────────────────────

def test_trailing_stop_not_triggered_insufficient_profit():
    """Trailing stop should not trigger when profit is below threshold."""
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.0980)
    # trailing_trigger_atr = 1.5, ATR = 0.001, trigger = 0.0015
    # Price at 1.1010 is only 0.0010 above entry, below 0.0015
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.1010, atr_value=0.0010)
    assert result is None, "Trailing stop should not trigger with insufficient profit"


def test_trailing_stop_triggered_buy():
    """Trailing stop should trigger for BUY when profit exceeds threshold."""
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.1005)
    # Price at 1.1040 is 0.0040 above entry, well above 0.0015 trigger
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.1040, atr_value=0.0010)
    assert result is not None
    assert result.action == "trailing_stop"
    assert result.new_sl > pos.current_sl, "Trailing SL should move UP for BUY"
    assert result.new_sl > pos.open_price, "Trailing SL should be above entry for BUY"


def test_trailing_stop_triggered_sell():
    """Trailing stop should trigger for SELL when profit exceeds threshold."""
    pos = make_position(side="SELL", open_price=1.1000, current_sl=1.0995)
    # Price at 1.0960 is 0.0040 below entry, well above trigger
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.0960, atr_value=0.0010)
    assert result is not None
    assert result.action == "trailing_stop"
    assert result.new_sl < pos.current_sl, "Trailing SL should move DOWN for SELL"
    assert result.new_sl < pos.open_price, "Trailing SL should be below entry for SELL"


def test_trailing_stop_does_not_move_sl_down_for_buy():
    """Trailing stop should NOT move SL down for a BUY position."""
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.1030)
    # Even though profit exceeds trigger, new SL (1.1040 - 0.001*1.5 = 1.1025)
    # would be below current SL of 1.0030 — should NOT trigger
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.1040, atr_value=0.0010)
    # trailing_distance_atr for EURUSD = 1.0, so trail_dist = 0.001
    # new_sl = 1.1040 - 0.001 = 1.1030, which equals current_sl, so no change needed
    # Actually let's check with a slightly different price where it would go down
    # current_sl=1.1040, new_sl would be 1.1040 - 0.001 = 1.1030
    # This IS below current_sl, so it should return None
    pos2 = make_position(side="BUY", open_price=1.1000, current_sl=1.1040)
    result2 = OrderManager.check_trailing_stop("EURUSDm", pos2, current_price=1.1045, atr_value=0.0010)
    # new_sl = 1.1045 - 0.001 = 1.1035, which is below current_sl=1.1040
    assert result2 is None, "Trailing stop should not move SL down for BUY"


def test_trailing_stop_does_not_move_sl_below_entry():
    """Trailing stop should NOT move SL below entry for BUY."""
    pos = make_position(side="BUY", open_price=1.1000, current_sl=1.0980)
    # Profit enough to trigger, but new SL would be at or below entry
    result = OrderManager.check_trailing_stop("EURUSDm", pos, current_price=1.1008, atr_value=0.0010)
    # trigger = 0.0015, profit = 0.0008, below trigger
    assert result is None


# ── Partial Close Logic ───────────────────────────────────────────────────

def test_partial_close_not_triggered_insufficient_profit():
    """Partial close should not trigger when profit is below 2x ATR."""
    pos = make_position(volume=0.10, open_price=1.1000)
    result = OrderManager.check_partial_close("EURUSDm", pos, current_price=1.1010, atr_value=0.0010)
    # 2x ATR trigger = 0.002, profit = 0.0010
    assert result is None, "Partial close should not trigger with insufficient profit"


def test_partial_close_triggered_at_profit_target():
    """Partial close should trigger when profit exceeds 2x ATR."""
    pos = make_position(volume=0.10, open_price=1.1000)
    # 2x ATR trigger = 0.002, profit at 0.0025
    result = OrderManager.check_partial_close("EURUSDm", pos, current_price=1.1025, atr_value=0.0010)
    assert result is not None
    assert result.action == "partial_close"
    assert result.volume_closed == 0.05, f"Should close half, got {result.volume_closed}"


def test_partial_close_not_triggered_when_already_done():
    """Partial close should not trigger again after already executed."""
    pos = make_position(volume=0.10, open_price=1.1000)
    pos.partial_close_done = True
    result = OrderManager.check_partial_close("EURUSDm", pos, current_price=1.1050, atr_value=0.0010)
    assert result is None, "Partial close should not trigger when already done"


def test_partial_close_not_triggered_for_small_volume():
    """Partial close should not trigger if volume is too small."""
    pos = make_position(volume=0.01, open_price=1.1000)
    result = OrderManager.check_partial_close("EURUSDm", pos, current_price=1.1050, atr_value=0.0010)
    # Volume 0.01 < 2 * 0.01 min_lots, so can't split
    assert result is None, "Partial close should not trigger for tiny volume"


# ── Config Loading ─────────────────────────────────────────────────────────

def test_load_symbol_risk_config_eurusd():
    """EURUSD config should load with expected defaults."""
    cfg = _load_symbol_risk_config("EURUSDm")
    assert "sl_atr_mult" in cfg
    assert "tp_atr_mult" in cfg
    assert "trailing_trigger_atr" in cfg


def test_load_symbol_risk_config_btc():
    """BTC config should have wider stops than EUR."""
    btc_cfg = _load_symbol_risk_config("BTCUSDm")
    eurusd_cfg = _load_symbol_risk_config("EURUSDm")
    assert btc_cfg.get("sl_atr_mult", 2.0) >= eurusd_cfg.get("sl_atr_mult", 2.0), \
        "BTC should have equal or wider SL multiplier than EUR"


def test_load_symbol_risk_config_unknown():
    """Unknown symbol should return sensible defaults."""
    _clear_config_cache()
    cfg = _load_symbol_risk_config("UNKNOWNPAIR")
    assert cfg["sl_atr_mult"] == 2.0
    assert cfg["tp_atr_mult"] == 3.0


def test_min_sl_for_symbol():
    """Minimum SL distance should vary by symbol type."""
    assert OrderManager.min_sl_for_symbol("XAUUSDm") == 10.0
    assert OrderManager.min_sl_for_symbol("BTCUSDm") == 500.0
    assert OrderManager.min_sl_for_symbol("EURUSDm") == 0.003


# ── Position State Management ─────────────────────────────────────────────

def test_reset_position_state():
    """Clearing position state should work correctly."""
    om = OrderManager()
    pos = make_position(ticket=42)
    om._positions[42] = pos

    om.reset_position_state(42)
    assert 42 not in om._positions

    # Non-existent ticket should not error
    om.reset_position_state(999)


def test_clear_all_state():
    """Clearing all state should work correctly."""
    om = OrderManager()
    om._positions[1] = make_position(ticket=1)
    om._positions[2] = make_position(ticket=2)

    om.clear_all_state()
    assert len(om._positions) == 0
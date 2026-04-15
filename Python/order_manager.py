"""
OrderManager — Unified order lifecycle management.

Consolidates SL/TP computation, breakeven triggers, trailing stop
management, and partial close logic that was previously scattered across
mt5_executor.py and action_translator.py.

Each method reads per-symbol risk config from configs/{symbol}.yaml
so that BTC gets wider stops than EUR, XAU gets wider trails, etc.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import yaml
from loguru import logger

# Conditional MT5 import
_mt5 = None
if os.name == "nt":
    try:
        import MetaTrader5 as mt5
        _mt5 = mt5
    except ImportError:
        pass


# ── Per-symbol config loader ──────────────────────────────────────────

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_config_cache: dict[str, dict] = {}
_config_cache_ts: dict[str, float] = {}
_CONFIG_TTL = 60.0  # Re-read config every 60 seconds


def _load_symbol_risk_config(symbol: str) -> dict:
    """Load risk config for a symbol from configs/{symbol}.yaml with TTL cache."""
    now = time.time()
    if symbol in _config_cache and (now - _config_cache_ts.get(symbol, 0)) < _CONFIG_TTL:
        return _config_cache[symbol]

    config_path = os.path.join(_root, "configs", f"{symbol}.yaml")
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            risk_cfg = cfg.get("risk", {})
            _config_cache[symbol] = risk_cfg
            _config_cache_ts[symbol] = now
            return risk_cfg
    except Exception as e:
        logger.warning(f"Failed to load config for {symbol}: {e}")

    # Default risk config (conservative)
    defaults = {
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 3.0,
        "trailing_trigger_atr": 1.5,
        "trailing_distance_atr": 1.5,
        "breakeven_trigger_atr": 1.0,
        "max_lots": 0.01,
        "max_positions_per_symbol": 2,
        "max_drawdown_pct": 10.0,
    }
    _config_cache[symbol] = defaults
    _config_cache_ts[symbol] = now
    return defaults


def _clear_config_cache():
    """Clear the config cache (useful for testing)."""
    _config_cache.clear()
    _config_cache_ts.clear()


# ── Position tracking ──────────────────────────────────────────────────

@dataclass
class ManagedPosition:
    """Tracks the lifecycle state of a position for order management."""
    ticket: int
    symbol: str
    side: str  # "BUY" or "SELL"
    volume: float
    open_price: float
    current_sl: float = 0.0
    current_tp: float = 0.0
    open_time: float = 0.0

    # Order management state
    breakeven_triggered: bool = False
    trailing_active: bool = False
    partial_close_done: bool = False

    # High-water mark for trailing stop calculation
    high_water_mark: float = 0.0
    low_water_mark: float = float("inf")


@dataclass
class OrderResult:
    """Result of an order management action."""
    success: bool
    action: str
    ticket: int = 0
    old_sl: float = 0.0
    new_sl: float = 0.0
    old_tp: float = 0.0
    new_tp: float = 0.0
    reason: str = ""
    volume_closed: float = 0.0


# ── OrderManager ────────────────────────────────────────────────────────

class OrderManager:
    """
    Unified order lifecycle manager.

    Responsibilities:
      1. Compute initial SL/TP from per-symbol ATR config
      2. Move SL to breakeven when price moves far enough in our favor
      3. Manage trailing stops after breakeven is hit
      4. Optionally execute partial closes at profit targets

    Usage:
        om = OrderManager()
        om.manage_all_positions()  # call periodically from main loop
    """

    # Minimum SL distance in price units per symbol type (same as MT5Executor)
    _MIN_SL = {
        "XAU": 10.0,
        "BTC": 500.0,
        "ETH": 30.0,
    }
    _DEFAULT_MIN_SL = 0.003  # 30 pips for FX

    def __init__(self, executor=None):
        """
        Args:
            executor: An MT5Executor or compatible object with get_positions(),
                      close_positions(), and _compute_atr_sl_tp() methods.
                      If None, OrderManager operates in dry-run mode.
        """
        self.executor = executor
        self._positions: dict[int, ManagedPosition] = {}

    # ── SL/TP Computation ───────────────────────────────────────────────

    @staticmethod
    def min_sl_for_symbol(symbol: str) -> float:
        """Minimum SL distance in price units for a symbol."""
        sym_upper = symbol.upper()
        for key, val in OrderManager._MIN_SL.items():
            if key in sym_upper:
                return val
        return OrderManager._DEFAULT_MIN_SL

    @staticmethod
    def compute_sl_tp(symbol: str, side: str, entry_price: float,
                       atr_value: float, sl_mult: float = None,
                       tp_mult: float = None) -> tuple[float, float]:
        """
        Compute SL/TP prices for an order.

        Args:
            symbol: Trading symbol (e.g. "XAUUSDm")
            side: "BUY" or "SELL"
            entry_price: Entry price
            atr_value: Current ATR value (raw, not multiplied)
            sl_mult: ATR multiplier for SL (reads from config if None)
            tp_mult: ATR multiplier for TP (reads from config if None)

        Returns:
            (sl_price, tp_price) tuple. 0.0 means no SL/TP.
        """
        risk_cfg = _load_symbol_risk_config(symbol)

        if sl_mult is None:
            sl_mult = risk_cfg.get("sl_atr_mult", 2.0)
        if tp_mult is None:
            tp_mult = risk_cfg.get("tp_atr_mult", 3.0)

        if atr_value <= 0:
            logger.warning(f"{symbol}: ATR is 0, cannot compute SL/TP")
            return 0.0, 0.0

        sl_distance = atr_value * sl_mult
        tp_distance = atr_value * tp_mult

        # Enforce minimum SL distance to prevent instant stop-outs
        min_sl = max(OrderManager.min_sl_for_symbol(symbol), atr_value * 0.5)
        if sl_distance < min_sl:
            logger.debug(f"{symbol}: SL={sl_distance:.5f} below minimum={min_sl:.5f}, widening")
            sl_distance = min_sl

        # Ensure TP is at least 1.5x SL for reasonable risk/reward
        if tp_distance < sl_distance * 1.5:
            tp_distance = sl_distance * 1.5

        if side.upper() == "BUY":
            sl_price = round(entry_price - sl_distance, 5)
            tp_price = round(entry_price + tp_distance, 5)
        else:  # SELL
            sl_price = round(entry_price + sl_distance, 5)
            tp_price = round(entry_price - tp_distance, 5)

        return sl_price, tp_price

    # ── Breakeven ────────────────────────────────────────────────────────

    @staticmethod
    def check_breakeven(symbol: str, position: ManagedPosition,
                        current_price: float, atr_value: float) -> Optional[OrderResult]:
        """
        Check if a position should have its SL moved to breakeven.

        Breakeven is triggered when price moves ATR * breakeven_trigger_atr
        in our favor from entry. The new SL is set to entry price (plus a
        small buffer for spread/commission coverage).

        Args:
            symbol: Trading symbol
            position: ManagedPosition to evaluate
            current_price: Current market price
            atr_value: Current ATR value

        Returns:
            OrderResult if breakeven should be triggered, None otherwise.
        """
        if position.breakeven_triggered:
            return None

        risk_cfg = _load_symbol_risk_config(symbol)
        trigger_atr = risk_cfg.get("breakeven_trigger_atr", 1.0)
        trigger_distance = atr_value * trigger_atr

        # Spread buffer to ensure breakeven SL covers costs (0.02% of price)
        spread_buffer = current_price * 0.0002

        is_buy = position.side.upper() == "BUY"

        if is_buy:
            profit_distance = current_price - position.open_price
            if profit_distance < trigger_distance:
                return None
            new_sl = round(position.open_price + spread_buffer, 5)
            # Only move SL up (never down for BUY)
            if position.current_sl > 0 and new_sl <= position.current_sl:
                return None
        else:  # SELL
            profit_distance = position.open_price - current_price
            if profit_distance < trigger_distance:
                return None
            new_sl = round(position.open_price - spread_buffer, 5)
            # Only move SL down (never up for SELL)
            if position.current_sl > 0 and new_sl >= position.current_sl:
                return None

        return OrderResult(
            success=True,
            action="breakeven",
            ticket=position.ticket,
            old_sl=position.current_sl,
            new_sl=new_sl,
            old_tp=position.current_tp,
            new_tp=position.current_tp,
            reason=f"breakeven triggered (profit_dist={profit_distance:.5f} >= trigger={trigger_distance:.5f})",
        )

    # ── Trailing Stop ────────────────────────────────────────────────────

    @staticmethod
    def check_trailing_stop(symbol: str, position: ManagedPosition,
                             current_price: float, atr_value: float) -> Optional[OrderResult]:
        """
        Check if a trailing stop should be applied.

        Trailing is triggered when price moves ATR * trailing_trigger_atr
        in our favor. The new SL is placed at current_price +/- ATR *
        trailing_distance_atr (for BUY/SELL respectively).

        Only moves SL in the favorable direction (up for BUY, down for SELL).

        Args:
            symbol: Trading symbol
            position: ManagedPosition to evaluate
            current_price: Current market price
            atr_value: Current ATR value

        Returns:
            OrderResult if trailing stop should be applied, None otherwise.
        """
        risk_cfg = _load_symbol_risk_config(symbol)
        trigger_atr = risk_cfg.get("trailing_trigger_atr", 1.5)
        distance_atr = risk_cfg.get("trailing_distance_atr", 1.5)

        trigger_distance = atr_value * trigger_atr
        trail_distance = atr_value * distance_atr

        is_buy = position.side.upper() == "BUY"

        if is_buy:
            profit_distance = current_price - position.open_price
            if profit_distance < trigger_distance:
                return None

            new_sl = round(current_price - trail_distance, 5)

            # Only move SL up
            if position.current_sl > 0 and new_sl <= position.current_sl:
                return None

            # Don't move SL below entry
            if new_sl <= position.open_price:
                return None

        else:  # SELL
            profit_distance = position.open_price - current_price
            if profit_distance < trigger_distance:
                return None

            new_sl = round(current_price + trail_distance, 5)

            # Only move SL down
            if position.current_sl > 0 and new_sl >= position.current_sl:
                return None

            # Don't move SL above entry
            if new_sl >= position.open_price:
                return None

        return OrderResult(
            success=True,
            action="trailing_stop",
            ticket=position.ticket,
            old_sl=position.current_sl,
            new_sl=new_sl,
            old_tp=position.current_tp,
            new_tp=position.current_tp,
            reason=f"trailing stop (trail_dist={trail_distance:.5f})",
        )

    # ── Partial Close ────────────────────────────────────────────────────

    @staticmethod
    def check_partial_close(symbol: str, position: ManagedPosition,
                             current_price: float, atr_value: float) -> Optional[OrderResult]:
        """
        Check if a partial close should be executed.

        Currently implements a simple "close half at 2x ATR profit" rule.
        This is conservative and can be extended with more sophisticated rules.

        Args:
            symbol: Trading symbol
            position: ManagedPosition to evaluate
            current_price: Current market price
            atr_value: Current ATR value

        Returns:
            OrderResult with partial close details, or None.
        """
        if position.partial_close_done:
            return None

        # Only partial close if volume is sufficient (need at least 2x min lots)
        min_lots = float(os.environ.get("AGI_MIN_LOTS", "0.01"))
        if position.volume < min_lots * 2:
            return None

        # Trigger at 2x ATR profit
        partial_trigger_atr = 2.0
        trigger_distance = atr_value * partial_trigger_atr
        close_volume = round(position.volume / 2, 2)

        # Ensure close_volume meets minimum lot size
        if close_volume < min_lots:
            return None

        is_buy = position.side.upper() == "BUY"

        if is_buy:
            profit_distance = current_price - position.open_price
        else:
            profit_distance = position.open_price - current_price

        if profit_distance < trigger_distance:
            return None

        return OrderResult(
            success=True,
            action="partial_close",
            ticket=position.ticket,
            reason=f"partial close at {partial_trigger_atr}x ATR profit",
            volume_closed=close_volume,
        )

    # ── Get Raw ATR ──────────────────────────────────────────────────────

    def get_raw_atr(self, symbol: str, atr_period: int = 14) -> float:
        """Get raw ATR value for a symbol.

        Delegates to the executor if available, otherwise returns 0.
        """
        if self.executor and hasattr(self.executor, "_get_raw_atr"):
            return self.executor._get_raw_atr(symbol, atr_period)
        return 0.0

    # ── Main Position Management Loop ───────────────────────────────────

    def manage_all_positions(self) -> list[OrderResult]:
        """
        Check all open positions and apply breakeven, trailing stops,
        and partial closes as needed.

        Should be called periodically (e.g. every 30-60 seconds) from
        the main trading loop.

        Returns:
            List of OrderResult for actions taken.
        """
        if not self.executor or not _mt5:
            return []

        results = []

        try:
            if not _mt5.initialize():
                logger.debug("OrderManager: MT5 init failed")
                return results

            try:
                positions = _mt5.positions_get()
                if not positions:
                    return results

                for p in positions:
                    result = self._manage_single_position(p)
                    if result:
                        results.append(result)
            finally:
                _mt5.shutdown()
        except Exception as e:
            logger.warning(f"OrderManager error: {e}")

        return results

    def _manage_single_position(self, mt5_position) -> Optional[OrderResult]:
        """Apply breakeven, trailing stop, and partial close to a single position."""
        symbol = mt5_position.symbol
        is_buy = mt5_position.type == 0  # 0 = BUY, 1 = SELL

        # Get current price
        tick = _mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        current_price = tick.bid if is_buy else tick.ask

        # Get ATR
        atr = self.get_raw_atr(symbol)
        if atr <= 0:
            return None

        # Build or update ManagedPosition from MT5 position
        pos = ManagedPosition(
            ticket=mt5_position.ticket,
            symbol=symbol,
            side="BUY" if is_buy else "SELL",
            volume=float(mt5_position.volume),
            open_price=float(mt5_position.price_open),
            current_sl=float(mt5_position.sl) if mt5_position.sl > 0 else 0.0,
            current_tp=float(mt5_position.tp) if mt5_position.tp > 0 else 0.0,
            open_time=float(mt5_position.time),
        )

        # Restore state from our tracking dict
        tracked = self._positions.get(pos.ticket)
        if tracked:
            pos.breakeven_triggered = tracked.breakeven_triggered
            pos.trailing_active = tracked.trailing_active
            pos.partial_close_done = tracked.partial_close_done

        # Update water marks
        if is_buy:
            pos.high_water_mark = max(current_price, tracked.high_water_mark if tracked else current_price)
        else:
            pos.low_water_mark = min(current_price, tracked.low_water_mark if tracked else current_price)

        self._positions[pos.ticket] = pos

        # Step 1: Check breakeven (only if not already triggered)
        if not pos.breakeven_triggered:
            be_result = self.check_breakeven(symbol, pos, current_price, atr)
            if be_result:
                apply_result = self._apply_sl_change(mt5_position, be_result.new_sl, pos.current_tp)
                if apply_result:
                    pos.breakeven_triggered = True
                    self._positions[pos.ticket] = pos
                    be_result.success = True
                    return be_result

        # Step 2: Check trailing stop
        trail_result = self.check_trailing_stop(symbol, pos, current_price, atr)
        if trail_result:
            apply_result = self._apply_sl_change(mt5_position, trail_result.new_sl, pos.current_tp)
            if apply_result:
                pos.trailing_active = True
                self._positions[pos.ticket] = pos
                trail_result.success = True
                return trail_result

        # Step 3: Check partial close
        partial_result = self.check_partial_close(symbol, pos, current_price, atr)
        if partial_result:
            apply_result = self._apply_partial_close(mt5_position, partial_result.volume_closed)
            if apply_result:
                pos.partial_close_done = True
                self._positions[pos.ticket] = pos
                partial_result.success = True
                return partial_result

        return None

    def _apply_sl_change(self, mt5_position, new_sl: float, current_tp: float) -> bool:
        """Apply SL/TP modification to an MT5 position."""
        request = {
            "action": _mt5.TRADE_ACTION_SLTP,
            "symbol": mt5_position.symbol,
            "position": mt5_position.ticket,
            "sl": new_sl,
        }
        if current_tp > 0:
            request["tp"] = current_tp

        result = _mt5.order_send(request)
        if result.retcode == _mt5.TRADE_RETCODE_DONE:
            old_sl = mt5_position.sl
            logger.info(
                f"OrderManager SL change: {mt5_position.symbol} #{mt5_position.ticket} "
                f"SL {old_sl:.5f} -> {new_sl:.5f}"
            )
            return True
        else:
            logger.warning(
                f"OrderManager SL change failed: {mt5_position.symbol} #{mt5_position.ticket} "
                f"retcode={result.retcode}"
            )
            return False

    def _apply_partial_close(self, mt5_position, close_volume: float) -> bool:
        """Close part of a position."""
        close_type = _mt5.ORDER_TYPE_SELL if mt5_position.type == 0 else _mt5.ORDER_TYPE_BUY
        tick = _mt5.symbol_info_tick(mt5_position.symbol)
        if tick is None:
            return False

        close_price = tick.bid if mt5_position.type == 0 else tick.ask

        request = {
            "action": _mt5.TRADE_ACTION_DEAL,
            "symbol": mt5_position.symbol,
            "volume": close_volume,
            "type": close_type,
            "position": mt5_position.ticket,
            "price": close_price,
            "comment": "OM partial close",
        }

        result = _mt5.order_send(request)
        if result.retcode == _mt5.TRADE_RETCODE_DONE:
            logger.info(
                f"OrderManager partial close: {mt5_position.symbol} #{mt5_position.ticket} "
                f"closed {close_volume} lots"
            )
            return True
        else:
            logger.warning(
                f"OrderManager partial close failed: {mt5_position.symbol} #{mt5_position.ticket} "
                f"retcode={result.retcode}"
            )
            return False

    # ── Lifecycle ───────────────────────────────────────────────────────

    def reset_position_state(self, ticket: int):
        """Remove tracking state for a closed position."""
        self._positions.pop(ticket, None)

    def clear_all_state(self):
        """Clear all position tracking state."""
        self._positions.clear()

    @property
    def active_positions(self) -> dict[int, ManagedPosition]:
        """Return current position tracking state (read-only snapshot)."""
        return dict(self._positions)
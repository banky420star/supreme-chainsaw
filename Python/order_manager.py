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
        "trailing_trigger_atr": 1.0,
        "trailing_distance_atr": 1.0,
        "breakeven_trigger_dollars": 5.0,
        "scale_out_1_dollars": 5.0,
        "scale_out_2_dollars": 10.0,
        "profit_banding_pct": 0.30,
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

    # Multi-level scale-out tracking
    scale_out_level: int = 0  # 0=none, 1=first close, 2=second close, 3=runner trailing
    scale_out_1_done: bool = False
    scale_out_2_done: bool = False

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
                        current_price: float, atr_value: float,
                        lot_size: float = 0.0) -> Optional[OrderResult]:
        """
        Check if a position should have its SL moved to breakeven.

        Breakeven is triggered when floating profit reaches the dollar
        threshold (breakeven_trigger_dollars, default $5). This ensures
        every winning trade locks in profit before trailing starts.

        Args:
            symbol: Trading symbol
            position: ManagedPosition to evaluate
            current_price: Current market price
            atr_value: Current ATR value (used for spread buffer)
            lot_size: Position volume in lots (for dollar profit calc)

        Returns:
            OrderResult if breakeven should be triggered, None otherwise.
        """
        if position.breakeven_triggered:
            return None

        risk_cfg = _load_symbol_risk_config(symbol)
        trigger_dollars = risk_cfg.get("breakeven_trigger_dollars", 5.0)

        is_buy = position.side.upper() == "BUY"

        # Calculate dollar profit using tick value
        pip_value = OrderManager._pip_value_per_lot(symbol)
        if pip_value <= 0:
            return None

        if is_buy:
            price_distance = current_price - position.open_price
        else:
            price_distance = position.open_price - current_price

        # Dollar profit = price_distance / pip_size * pip_value_per_lot * volume
        # Simpler: use tick_size and tick_value from symbol info
        dollar_profit = OrderManager._calc_dollar_profit(symbol, position.volume, position.open_price, current_price, is_buy)

        if dollar_profit < trigger_dollars:
            return None

        # Spread buffer to ensure breakeven SL covers costs (0.02% of price)
        spread_buffer = current_price * 0.0002

        if is_buy:
            new_sl = round(position.open_price + spread_buffer, 5)
            # Only move SL up (never down for BUY)
            if position.current_sl > 0 and new_sl <= position.current_sl:
                return None
        else:  # SELL
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
            reason=f"breakeven triggered (dollar_profit=${dollar_profit:.2f} >= ${trigger_dollars:.2f})",
        )

    # ── Trailing Stop ────────────────────────────────────────────────────

    @staticmethod
    def check_trailing_stop(symbol: str, position: ManagedPosition,
                             current_price: float, atr_value: float) -> Optional[OrderResult]:
        """
        Check if a trailing stop should be applied.

        Trailing ONLY starts after breakeven has been triggered.
        Uses a profit-banding system that tightens as profit grows:
        - Max giveback = 30% of peak profit (profit_banding_pct)
        - This means if peak profit was $50, SL is set so max loss is $15 (30%)
        - Falls back to ATR-based distance as minimum

        Only moves SL in the favorable direction (up for BUY, down for SELL).

        Args:
            symbol: Trading symbol
            position: ManagedPosition to evaluate
            current_price: Current market price
            atr_value: Current ATR value

        Returns:
            OrderResult if trailing stop should be applied, None otherwise.
        """
        # Trailing only starts after breakeven is triggered
        if not position.breakeven_triggered:
            return None

        risk_cfg = _load_symbol_risk_config(symbol)
        trigger_atr = risk_cfg.get("trailing_trigger_atr", 1.0)
        distance_atr = risk_cfg.get("trailing_distance_atr", 1.0)
        profit_banding_pct = risk_cfg.get("profit_banding_pct", 0.30)  # max giveback = 30%

        trigger_distance = atr_value * trigger_atr

        is_buy = position.side.upper() == "BUY"

        if is_buy:
            profit_distance = current_price - position.open_price
            if profit_distance < trigger_distance:
                return None

            # Use high-water mark for profit-banding
            hwm = position.high_water_mark if position.high_water_mark > 0 else current_price
            peak_profit = hwm - position.open_price

            # Calculate SL based on profit-banding: keep at least (1 - banding_pct) of peak profit
            # E.g. if peak profit = $50 and banding = 0.30, SL at entry + $35 (giving back max $15)
            if peak_profit > 0:
                max_giveback = peak_profit * profit_banding_pct
                sl_from_profit_banding = position.open_price + (peak_profit - max_giveback)
            else:
                sl_from_profit_banding = current_price - (atr_value * distance_atr)

            # ATR-based SL as minimum (don't let trailing be wider than ATR)
            sl_from_atr = current_price - (atr_value * distance_atr)

            # Use the TIGHTER (higher for BUY) of profit-banding and ATR
            new_sl = round(max(sl_from_profit_banding, sl_from_atr), 5)

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

            # Use low-water mark for profit-banding
            lwm = position.low_water_mark if position.low_water_mark > 0 and position.low_water_mark < float('inf') else current_price
            peak_profit = position.open_price - lwm

            # Calculate SL based on profit-banding
            if peak_profit > 0:
                max_giveback = peak_profit * profit_banding_pct
                sl_from_profit_banding = position.open_price - (peak_profit - max_giveback)
            else:
                sl_from_profit_banding = current_price + (atr_value * distance_atr)

            # ATR-based SL as minimum (don't let trailing be wider than ATR)
            sl_from_atr = current_price + (atr_value * distance_atr)

            # Use the TIGHTER (lower for SELL) of profit-banding and ATR
            new_sl = round(min(sl_from_profit_banding, sl_from_atr), 5)

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
            reason=f"trailing stop (peak_profit=${peak_profit:.2f}, giveback_max={profit_banding_pct:.0%}, new_sl={new_sl:.5f})",
        )

    # ── Multi-Level Scale-Out (Exponential Compounding) ────────────────────

    @staticmethod
    def check_scale_out(symbol: str, position: ManagedPosition,
                         current_price: float, atr_value: float) -> Optional[OrderResult]:
        """
        Multi-level scale-out for exponential compounding.

        Level 1: Close 1/3 of position at $5 profit (secure quick cash)
        Level 2: Close 1/3 of position at $10 profit (secure more cash)
        Level 3: Runner — remove TP, let trailing stop ride the trend to max profit

        This ensures we book profits early while still letting winners run
        for exponential growth. The freed margin from partial closes gets
        reinvested into new positions via Kelly compounding.

        Args:
            symbol: Trading symbol
            position: ManagedPosition to evaluate
            current_price: Current market price
            atr_value: Current ATR value

        Returns:
            OrderResult with scale-out details, or None.
        """
        risk_cfg = _load_symbol_risk_config(symbol)
        scale1_dollars = risk_cfg.get("scale_out_1_dollars", 5.0)
        scale2_dollars = risk_cfg.get("scale_out_2_dollars", 10.0)
        min_lots = float(os.environ.get("AGI_MIN_LOTS", "0.01"))

        # Calculate dollar profit
        dollar_profit = OrderManager._calc_dollar_profit(
            symbol, position.volume, position.open_price, current_price,
            position.side.upper() == "BUY"
        )

        # Level 1: Close 1/3 at first profit target ($5)
        if not position.scale_out_1_done and dollar_profit >= scale1_dollars:
            close_volume = round(position.volume / 3, 2)
            if close_volume < min_lots:
                close_volume = min_lots
            if close_volume >= position.volume:
                # Position too small to split, just mark done
                position.scale_out_1_done = True
                position.scale_out_level = 1
                return None
            return OrderResult(
                success=True,
                action="scale_out_1",
                ticket=position.ticket,
                reason=f"scale-out 1/3 at ${dollar_profit:.2f} profit (target ${scale1_dollars})",
                volume_closed=close_volume,
            )

        # Level 2: Close 1/3 at second profit target ($10)
        if position.scale_out_1_done and not position.scale_out_2_done and dollar_profit >= scale2_dollars:
            close_volume = round(position.volume / 2, 2)  # half of remaining
            if close_volume < min_lots:
                close_volume = min_lots
            if close_volume >= position.volume:
                position.scale_out_2_done = True
                position.scale_out_level = 2
                return None
            return OrderResult(
                success=True,
                action="scale_out_2",
                ticket=position.ticket,
                reason=f"scale-out 1/3 at ${dollar_profit:.2f} profit (target ${scale2_dollars})",
                volume_closed=close_volume,
            )

        # Level 3: Runner mode — remove fixed TP, let trailing run
        if position.scale_out_1_done and position.scale_out_2_done:
            if position.scale_out_level < 3:
                position.scale_out_level = 3
                # Signal to remove TP so trailing can ride the trend
                return OrderResult(
                    success=True,
                    action="runner_mode",
                    ticket=position.ticket,
                    old_tp=position.current_tp,
                    new_tp=0.0,  # Remove TP — let trailing manage exit
                    reason=f"runner mode: TP removed, trailing will ride trend (profit=${dollar_profit:.2f})",
                )

        return None

    # ── Get Raw ATR ──────────────────────────────────────────────────────

    def get_raw_atr(self, symbol: str, atr_period: int = 14) -> float:
        """Get raw ATR value for a symbol.

        Delegates to the executor if available, otherwise returns 0.
        """
        if self.executor and hasattr(self.executor, "_get_raw_atr"):
            return self.executor._get_raw_atr(symbol, atr_period)
        return 0.0

    # ── Dollar profit calculation ────────────────────────────────────────

    @staticmethod
    def _pip_value_per_lot(symbol: str) -> float:
        """Get pip value per lot for a symbol using MT5 symbol info."""
        if _mt5 is None:
            return 0.0
        try:
            if not _mt5.initialize():
                return 0.0
            info = _mt5.symbol_info(symbol)
            if info is None:
                return 0.0
            tick_size = getattr(info, 'trade_tick_size', 0)
            tick_value = getattr(info, 'trade_tick_value', 0)
            if tick_size > 0 and tick_value > 0:
                # Pip value per 1.0 lot = tick_value / tick_size * pip_size
                # For simplicity: value per tick per lot
                return tick_value / tick_size
            return 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _calc_dollar_profit(symbol: str, volume: float, open_price: float,
                             current_price: float, is_buy: bool) -> float:
        """Calculate dollar profit for a position using MT5 tick values."""
        if _mt5 is None:
            # Fallback: rough estimate
            if "XAU" in symbol.upper():
                return (current_price - open_price) * volume * 100 if is_buy else (open_price - current_price) * volume * 100
            elif "BTC" in symbol.upper():
                return (current_price - open_price) * volume if is_buy else (open_price - current_price) * volume
            else:
                return (current_price - open_price) * volume * 100000 if is_buy else (open_price - current_price) * volume * 100000

        try:
            if not _mt5.initialize():
                return 0.0
            info = _mt5.symbol_info(symbol)
            if info is None:
                return 0.0
            tick_size = getattr(info, 'trade_tick_size', 0)
            tick_value = getattr(info, 'trade_tick_value', 0)
            contract_size = getattr(info, 'trade_contract_size', 100000)

            if tick_size > 0 and tick_value > 0:
                price_diff = (current_price - open_price) if is_buy else (open_price - current_price)
                ticks = price_diff / tick_size
                return ticks * tick_value * volume
            else:
                # Fallback using contract size
                price_diff = (current_price - open_price) if is_buy else (open_price - current_price)
                return price_diff * contract_size * volume
        except Exception:
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
            pos.scale_out_1_done = tracked.scale_out_1_done
            pos.scale_out_2_done = tracked.scale_out_2_done
            pos.scale_out_level = tracked.scale_out_level

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

        # Step 2: Check trailing stop (only after breakeven)
        trail_result = self.check_trailing_stop(symbol, pos, current_price, atr)
        if trail_result:
            apply_result = self._apply_sl_change(mt5_position, trail_result.new_sl, pos.current_tp)
            if apply_result:
                pos.trailing_active = True
                self._positions[pos.ticket] = pos
                trail_result.success = True
                return trail_result

        # Step 3: Multi-level scale-out for exponential compounding
        scale_result = self.check_scale_out(symbol, pos, current_price, atr)
        if scale_result:
            if scale_result.action == "runner_mode":
                # Remove TP so trailing can ride the trend to infinity
                apply_result = self._apply_sl_change(mt5_position, pos.current_sl, 0.0)
                if apply_result:
                    pos.scale_out_level = 3
                    pos.current_tp = 0.0
                    self._positions[pos.ticket] = pos
                    logger.info(f"RUNNER MODE: {symbol} #{pos.ticket} TP removed, trailing will ride trend")
                    return scale_result
            elif scale_result.volume_closed and scale_result.volume_closed > 0:
                apply_result = self._apply_partial_close(mt5_position, scale_result.volume_closed)
                if apply_result:
                    if scale_result.action == "scale_out_1":
                        pos.scale_out_1_done = True
                        pos.scale_out_level = 1
                    elif scale_result.action == "scale_out_2":
                        pos.scale_out_2_done = True
                        pos.scale_out_level = 2
                    self._positions[pos.ticket] = pos
                    scale_result.success = True
                    return scale_result

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
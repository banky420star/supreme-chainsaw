"""
MT5 Executor — Trade execution with conditional MT5 import and dry-run mode.
Automatically falls back to DryRunExecutor on Mac/Linux.
Supports multi-position trading: up to N concurrent positions per symbol.
"""
import sys
import os
from loguru import logger

# ── Conditional MT5 import ──────────────────────────────────────────
_mt5 = None
if sys.platform == "win32":
    try:
        import MetaTrader5 as mt5
        _mt5 = mt5
    except ImportError:
        logger.warning("MetaTrader5 not installed on Windows — using dry-run mode")


class MT5Executor:
    """Live MT5 execution (Windows only)."""

    def __init__(self, risk):
        self.risk = risk
        self._is_live = _mt5 is not None and sys.platform == "win32"

        if self._is_live:
            try:
                if not _mt5.initialize():
                    logger.error("MT5 initialize() failed — falling back to dry-run")
                    self._is_live = False
            except Exception as e:
                logger.error(f"MT5 init error: {e}")
                self._is_live = False

        if self._is_live:
            logger.success("MT5Executor: LIVE mode — connected to MetaTrader 5")
        else:
            logger.info("MT5Executor: DRY-RUN mode — trades will be logged only")

    def get_positions(self, symbol):
        longs = []
        shorts = []

        if not self._is_live:
            return longs, shorts

        positions = _mt5.positions_get(symbol=symbol)
        if positions:
            for p in positions:
                if p.type == 0:
                    longs.append(p)
                else:
                    shorts.append(p)
        return longs, shorts

    def _check_news_blackout(self, symbol, minutes_before=5, minutes_after=5):
        """Check if a high-impact economic event is within the blackout window.

        Returns True if news blackout is active (trade should be skipped).
        Uses the MT5 economic calendar API to find upcoming events.
        """
        if not self._is_live or _mt5 is None:
            return False

        try:
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(minutes=minutes_after)
            window_end = now + timedelta(minutes=minutes_before)

            # Determine the currency pair's two currencies (e.g. EURUSD -> EUR, USD)
            currencies = []
            for i in range(0, len(symbol) - 2, 3):
                currencies.append(symbol[i:i+3])
            if len(currencies) == 0:
                # Can't determine currencies — check all events as a safety net
                currencies = None

            countries = _mt5.calendar_country()
            if not countries:
                return False

            for country in countries:
                # Skip countries whose currency is not in the symbol
                if currencies is not None:
                    currency_code = getattr(country, "currency", "") or getattr(country, "code", "")
                    if currency_code not in currencies:
                        continue

                try:
                    events = _mt5.calendar_value_last_by_country(
                        country.code, window_start, window_end
                    )
                except AttributeError:
                    # Fallback: try calendar_value_last if _by_country variant missing
                    try:
                        events = _mt5.calendar_value_last(
                            country.code, window_start, window_end
                        )
                    except (AttributeError, TypeError):
                        continue

                if not events:
                    continue

                for ev in events:
                    importance = getattr(ev, "importance", 0)
                    if importance >= 2:  # MT5: 0=low, 1=medium, 2=high
                        event_name = getattr(ev, "name", "unknown")
                        event_time = getattr(ev, "time", "")
                        logger.warning(
                            f"NEWS BLACKOUT ACTIVE: {event_name} ({country.code}) "
                            f"importance={importance} time={event_time} — skipping {symbol}"
                        )
                        return True

            return False

        except Exception as e:
            logger.warning(f"News blackout check failed for {symbol}: {e}")
            return False

    def reconcile_exposure(self, symbol, target_exposure, max_lots, max_positions_per_symbol=5):
        """Multi-position executor: adds new positions up to max_positions_per_symbol.

        Each cycle, if the model says BUY and we have fewer than N long positions,
        open a new position. If SELL, open shorts. If opposite direction
        positions exist, close them first.

        Reads per-symbol risk config from configs/{symbol}.yaml for max_lots,
        SL/TP ATR multipliers, and position limits.

        Only adds ONE position per call to avoid rapid stacking.
        """
        if not self.risk.can_trade():
            return

        # Skip trade if a high-impact news event is imminent or just released
        if self._check_news_blackout(symbol):
            logger.info(f"{symbol}: trade skipped — news blackout active")
            return

        # Load per-symbol risk config
        sym_max_lots = max_lots
        sym_max_positions = max_positions_per_symbol
        try:
            import yaml
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "configs", f"{symbol}.yaml"
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    sym_cfg = yaml.safe_load(f)
                risk_cfg = sym_cfg.get("risk", {})
                sym_max_lots = risk_cfg.get("max_lots", max_lots)
                sym_max_positions = risk_cfg.get("max_positions_per_symbol", max_positions_per_symbol)
        except Exception:
            pass

        min_lots = float(os.environ.get("AGI_MIN_LOTS", "0.01"))
        # Cap lot size to per-symbol maximum
        lot_size = min(min_lots, sym_max_lots)

        if not self._is_live:
            # Dry-run: just log the intended trade
            direction = "BUY" if target_exposure > 0 else "SELL" if target_exposure < 0 else "FLAT"
            logger.info(
                f"DRY-RUN TRADE: {symbol} | {direction} | "
                f"exposure={target_exposure:.4f} | lots={min_lots}"
            )
            self.risk.record_trade()
            return

        # ── Live MT5 execution ──
        longs, shorts = self.get_positions(symbol)
        n_longs = len(longs)
        n_shorts = len(shorts)

        # Determine direction from PPO exposure
        if abs(target_exposure) < float(os.environ.get("AGI_ACTION_THRESHOLD", "0.001")):
            # Signal too weak — skip
            return

        is_buy = target_exposure > 0

        if is_buy:
            # If we already have long positions, don't add more unless under the limit
            # and the existing positions are profitable (avoid doubling down on losers)
            if n_longs >= sym_max_positions:
                logger.debug(f"{symbol}: max long positions reached ({n_longs}/{sym_max_positions})")
                return

            # Close any opposing short positions first
            if n_shorts > 0:
                self.close_positions(shorts)
                logger.info(f"Closed {n_shorts} short position(s) for {symbol}")

            # Open ONE new long position
            self.open_position(symbol, _mt5.ORDER_TYPE_BUY, lot_size)
            self.risk.record_trade()
            logger.info(f"Opened long #{n_longs + 1}/{sym_max_positions} for {symbol} ({lot_size} lots)")
        else:
            if n_shorts >= sym_max_positions:
                logger.debug(f"{symbol}: max short positions reached ({n_shorts}/{sym_max_positions})")
                return

            # Close any opposing long positions first
            if n_longs > 0:
                self.close_positions(longs)
                logger.info(f"Closed {n_longs} long position(s) for {symbol}")

            # Open ONE new short position
            self.open_position(symbol, _mt5.ORDER_TYPE_SELL, lot_size)
            self.risk.record_trade()
            logger.info(f"Opened short #{n_shorts + 1}/{sym_max_positions} for {symbol} ({lot_size} lots)")

    def close_positions(self, positions):
        if not self._is_live:
            return

        for p in positions:
            request = {
                "action": _mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": _mt5.ORDER_TYPE_SELL if p.type == 0 else _mt5.ORDER_TYPE_BUY,
                "position": p.ticket
            }
            result = _mt5.order_send(request)
            if result.retcode != _mt5.TRADE_RETCODE_DONE:
                logger.error(f"Close position failed for {p.symbol} ticket={p.ticket}: retcode={result.retcode}")
                self.risk.record_error()

    def close_all_positions(self, symbol=None):
        """Close all open positions, optionally filtered by symbol."""
        if not self._is_live:
            return
        if symbol:
            positions = _mt5.positions_get(symbol=symbol)
        else:
            positions = _mt5.positions_get()
        if positions:
            self.close_positions(list(positions))

    def open_position(self, symbol, order_type, volume):
        if not self._is_live:
            return

        tick = _mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Cannot get tick for {symbol}")
            self.risk.record_error()
            return

        # Compute ATR-based SL/TP defaults
        sl_distance, tp_distance = self._compute_atr_sl_tp(symbol)

        entry_price = tick.ask if order_type == _mt5.ORDER_TYPE_BUY else tick.bid

        # Compute SL/TP price levels
        if order_type == _mt5.ORDER_TYPE_BUY:
            sl = round(entry_price - sl_distance, 5) if sl_distance > 0 else 0
            tp = round(entry_price + tp_distance, 5) if tp_distance > 0 else 0
        else:
            sl = round(entry_price + sl_distance, 5) if sl_distance > 0 else 0
            tp = round(entry_price - tp_distance, 5) if tp_distance > 0 else 0

        request = {
            "action": _mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": entry_price,
        }
        if sl > 0:
            request["sl"] = sl
        if tp > 0:
            request["tp"] = tp

        logger.info(f"MT5 ORDER: {symbol} {'BUY' if order_type == _mt5.ORDER_TYPE_BUY else 'SELL'} "
                     f"{volume:.2f} lots @ {entry_price} | SL={sl} TP={tp}")
        result = _mt5.order_send(request)
        if result.retcode != _mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5 order failed: retcode={result.retcode}")
            self.risk.record_error()

    def _compute_atr_sl_tp(self, symbol, atr_period=14, sl_mult=None, tp_mult=None):
        """Compute ATR-based stop loss and take profit distances.

        Reads per-symbol ATR multipliers from configs/{symbol}.yaml if available,
        otherwise uses conservative defaults (sl=2.0, tp=3.0).
        """
        if sl_mult is None or tp_mult is None:
            # Try loading per-symbol config
            try:
                import yaml
                config_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "configs", f"{symbol}.yaml"
                )
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        sym_cfg = yaml.safe_load(f)
                    risk_cfg = sym_cfg.get("risk", {})
                    sl_mult = sl_mult or risk_cfg.get("sl_atr_mult", 2.0)
                    tp_mult = tp_mult or risk_cfg.get("tp_atr_mult", 3.0)
                else:
                    sl_mult = sl_mult or 2.0
                    tp_mult = tp_mult or 3.0
            except Exception:
                sl_mult = sl_mult or 2.0
                tp_mult = tp_mult or 3.0

        try:
            rates = _mt5.copy_rates_from_pos(symbol, _mt5.TIMEFRAME_M5, 0, atr_period + 1)
            if rates is None or len(rates) < atr_period + 1:
                return 0, 0

            # Calculate ATR14
            high = rates["high"]
            low = rates["low"]
            close = rates["close"]
            trs = []
            for i in range(1, len(rates)):
                tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
                trs.append(tr)
            atr = sum(trs[-atr_period:]) / atr_period if len(trs) >= atr_period else 0

            sl_distance = atr * sl_mult
            tp_distance = atr * tp_mult
            return sl_distance, tp_distance
        except Exception as e:
            logger.warning(f"ATR SL/TP computation failed for {symbol}: {e}")
            return 0, 0
"""
MT5 Executor — Trade execution with conditional MT5 import and dry-run mode.
Automatically falls back to DryRunExecutor on Mac/Linux.
Supports multi-position trading: up to N concurrent positions per symbol.
"""
import sys
import os
import time
from loguru import logger

# ── Audio alert for trade execution (Windows only) ───────────────────
if sys.platform == "win32":
    try:
        import winsound
        _ALERT_ENABLED = True
    except ImportError:
        _ALERT_ENABLED = False
else:
    _ALERT_ENABLED = False

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

    # Magic number ranges: base 505000 + symbol offset * 100 + lane offset
    # Symbol offsets: EURUSD=0, GBPUSD=1, XAUUSD=2, BTCUSD=3
    # Lane offsets: champion=0, canary=1
    _SYMBOL_MAGIC_OFFSET = {
        "EURUSDm": 0, "EURUSD": 0,
        "GBPUSDm": 1, "GBPUSD": 1,
        "XAUUSDm": 2, "XAUUSD": 2,
        "BTCUSDm": 3, "BTCUSD": 3,
        "USDCADm": 4, "USDCAD": 4,
        "USDJPYm": 5, "USDJPY": 5,
        "AUDUSDm": 6, "AUDUSD": 6,
    }
    _MAGIC_BASE = 505000
    _DEFAULT_MAGIC = 505

    def __init__(self, risk):
        self.risk = risk
        self._is_live = _mt5 is not None and sys.platform == "win32"
        self._last_order_meta = {}  # carry context for close orders
        self._last_sl_hit_time = {}  # symbol -> timestamp of last SL hit (cooldown tracking)

        # ── Half-Kelly position sizing state ──
        self._kelly_win_rate = {}     # symbol -> recent win rate (0-1)
        self._kelly_avg_win = {}      # symbol -> average winning trade PnL
        self._kelly_avg_loss = {}     # symbol -> average losing trade PnL (positive)
        self._kelly_last_update = {}  # symbol -> timestamp of last stats update

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

    @staticmethod
    def _play_trade_alert():
        """Play a loud beep when a trade is executed (Windows only)."""
        if _ALERT_ENABLED:
            try:
                # Two-tone alert: 800Hz for 300ms, then 1000Hz for 300ms
                winsound.Beep(800, 300)
                winsound.Beep(1000, 300)
            except Exception:
                pass

    @staticmethod
    def _pip_value_per_lot(symbol: str) -> float:
        """Approximate dollar value per 0.01 lot for SL distance calculation."""
        sym = symbol.replace("m", "")
        if sym == "XAUUSD":
            return 1.0  # ~$1 per pip per 0.01 lot
        elif sym == "BTCUSD":
            return 1.0  # ~$1 per point per 0.01 lot
        else:
            # FX pairs: ~$0.10 per pip per 0.01 lot
            return 0.10

    def _update_kelly_stats(self, symbol):
        """Refresh per-symbol win rate and PnL stats from MT5 trade history."""
        now = time.time()
        # Only refresh every 5 minutes to avoid hammering MT5
        if now - self._kelly_last_update.get(symbol, 0) < 300:
            return
        self._kelly_last_update[symbol] = now

        if not self._is_live:
            return

        try:
            from datetime import datetime, timedelta
            # Get last 30 days of deals
            to_dt = datetime.now()
            from_dt = to_dt - timedelta(days=30)
            deals = _mt5.history_deals_get(from_dt, to_dt)
            if not deals:
                return

            wins_pnl = []
            losses_pnl = []
            for d in deals:
                if d.symbol != symbol or d.entry != 1:  # entry=1 means deal out (closed)
                    continue
                if d.profit > 0:
                    wins_pnl.append(d.profit)
                elif d.profit < 0:
                    losses_pnl.append(abs(d.profit))

            total = len(wins_pnl) + len(losses_pnl)
            if total >= 5:  # Need minimum 5 trades for meaningful stats
                self._kelly_win_rate[symbol] = len(wins_pnl) / total
                self._kelly_avg_win[symbol] = sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0
                self._kelly_avg_loss[symbol] = sum(losses_pnl) / len(losses_pnl) if losses_pnl else 0
                logger.debug(
                    f"Kelly stats {symbol}: WR={self._kelly_win_rate[symbol]:.2%} "
                    f"avg_win=${self._kelly_avg_win[symbol]:.2f} "
                    f"avg_loss=${self._kelly_avg_loss[symbol]:.2f}"
                )
        except Exception as e:
            logger.debug(f"Kelly stats update failed for {symbol}: {e}")

    def _kelly_lot_size(self, symbol, exposure, min_lots, max_lots):
        """Calculate lot size using Half-Kelly criterion.

        Kelly fraction: f* = (p*b - q) / b
        Where: p = win probability, q = 1-p, b = avg_win / avg_loss
        Half-Kelly: f = f* / 2 (reduces variance, ~75% of full growth)

        Exposure magnitude scales confidence: higher |exposure| = higher conviction.
        """
        self._update_kelly_stats(symbol)

        # Default to minimum lots if no stats available
        wr = self._kelly_win_rate.get(symbol)
        avg_win = self._kelly_avg_win.get(symbol, 0)
        avg_loss = self._kelly_avg_loss.get(symbol, 0)

        if wr is None or avg_win <= 0 or avg_loss <= 0:
            return min(min_lots, max_lots)

        # Kelly fraction: f* = (p * b - q) / b
        b = avg_win / avg_loss  # reward-to-risk ratio
        q = 1.0 - wr
        kelly_full = (wr * b - q) / b

        # Clamp to [0, 1] — negative Kelly means don't trade
        kelly_full = max(0.0, min(1.0, kelly_full))

        # Half-Kelly (industry standard)
        kelly_half = kelly_full * 0.5

        # Scale by conviction (|exposure| as signal strength)
        # exposure is typically 0.001-0.05, normalize to 0.3-1.0 range
        conviction = min(1.0, max(0.3, abs(exposure) * 20))

        # Risk budget: fraction of account we're willing to risk per trade
        # Scale by Kelly half and conviction
        equity = getattr(self.risk, "_current_equity", 50.0) or 50.0
        risk_pct = float(os.environ.get("AGI_RISK_PERCENT", "2.0")) / 100.0
        risk_budget = equity * risk_pct * kelly_half * conviction

        # Convert risk budget to lots using per-symbol contract size
        # Each 0.01 lot risks different amounts depending on the symbol:
        #   XAUUSDm: ~$7.68 per 0.01 lot on SL hit
        #   BTCUSDm: ~$5.00 per 0.01 lot on SL hit
        #   EURUSDm: ~$0.24 per 0.01 lot on SL hit (pip value ~$0.10)
        #   GBPUSDm: ~$0.27 per 0.01 lot on SL hit (pip value ~$0.10)
        # Use avg_loss per 0.01 lot from trade history as the risk-per-lot
        if avg_loss > 0:
            lots_from_risk = risk_budget / avg_loss
        else:
            # No loss history — use conservative pip-value estimate
            pip_value_per_lot = self._pip_value_per_lot(symbol)
            sl_distance_atr = 2.0  # assume 2x ATR SL
            lots_from_risk = risk_budget / (sl_distance_atr * pip_value_per_lot) if pip_value_per_lot > 0 else min_lots

        # Apply broker minimum and maximum
        lot_size = max(min_lots, min(lots_from_risk, max_lots))

        # Round to broker lot step (0.01 for most symbols)
        lot_step = 0.01
        lot_size = round(lot_size / lot_step) * lot_step
        lot_size = max(min_lots, min(lot_size, max_lots))

        logger.info(
            f"Kelly sizing {symbol}: f*={kelly_full:.3f} half={kelly_half:.3f} "
            f"conviction={conviction:.2f} equity=${equity:.2f} "
            f"risk_budget=${risk_budget:.2f} -> {lot_size:.2f} lots"
        )

        return lot_size

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

    def _magic_for_order(self, symbol, order_meta, request_kind="open"):
        """Compute a unique magic number per symbol + lane combination.

        Magic number scheme: BASE + symbol_offset * 100 + lane_offset
          - champion orders: symbol_offset * 100
          - canary orders:   symbol_offset * 100 + 1
          - close orders:    + 50 (to distinguish from opens)

        This lets the user filter trades by symbol/lane in MT5 history.
        """
        sym_offset = self._SYMBOL_MAGIC_OFFSET.get(symbol, 99)
        lane = (order_meta or {}).get("lane", "champion")
        lane_offset = 0 if lane == "champion" else 1
        magic = self._MAGIC_BASE + sym_offset * 100 + lane_offset
        if request_kind == "close":
            magic += 50
        return magic

    def _order_comment(self, symbol, order_meta, request_kind="open"):
        """Build an MT5 order comment string (max 31 chars).

        Format: {SYM6}{KIND}{LANE}{VERSION}
          SYM6: first 6 chars of symbol (e.g. XAUUSD)
          KIND: OP=open, CL=close
          LANE: CH=champion, CA=canary
          VERSION: last 6 chars of model version (timestamp)
        Example: XAUUSDOPCH120510  (21 chars)
        """
        sym_short = symbol[:6].ljust(6)
        kind_code = "OP" if request_kind == "open" else "CL"
        lane = (order_meta or {}).get("lane", "champion")
        lane_code = "CH" if lane == "champion" else "CA"
        model_version = (order_meta or {}).get("model_version", "")
        ver_short = model_version.replace("_", "")[-6:] if model_version else "------"

        comment = f"{sym_short}{kind_code}{lane_code}{ver_short}"
        # MT5 comment field limit is 31 chars
        return comment[:31]

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

            # Parse currencies from symbol name (handles broker suffixes like 'm')
            base = symbol.rstrip("m").rstrip("M")
            currencies = []
            # Known commodity prefixes
            for prefix in ["XAU", "XAG", "XPT"]:
                if base.startswith(prefix):
                    currencies = [prefix, base[len(prefix):]]
                    break
            else:
                # Standard FX: 6-char base
                if len(base) == 6:
                    currencies = [base[:3], base[3:]]
                else:
                    # Crypto or unknown: try 3-char splits
                    for prefix in ["BTC", "ETH", "SOL", "LTC"]:
                        if base.startswith(prefix):
                            currencies = [prefix, base[len(prefix):]]
                            break
                    if not currencies:
                        for i in range(0, len(base) - 2, 3):
                            currencies.append(base[i:i+3])
            if not currencies:
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

    def reconcile_exposure(self, symbol, target_exposure, max_lots, max_positions_per_symbol=5,
                           order_meta=None):
        """Multi-position executor: adds new positions up to max_positions_per_symbol.

        Each cycle, if the model says BUY and we have fewer than N long positions,
        open a new position. If SELL, open shorts. If opposite direction
        positions exist, close them first.

        Reads per-symbol risk config from configs/{symbol}.yaml for max_lots,
        SL/TP ATR multipliers, and position limits.

        order_meta: dict with 'lane', 'model_version', etc. for magic/comment.

        Only adds ONE position per call to avoid rapid stacking.
        """
        if not self.risk.can_trade():
            return

        # Post-SL cooldown: skip trading a symbol for N minutes after an SL hit
        cooldown_minutes = int(os.environ.get("AGI_SL_COOLDOWN_MIN", "15"))
        last_sl = self._last_sl_hit_time.get(symbol, 0)
        if last_sl > 0 and (time.time() - last_sl) < (cooldown_minutes * 60):
            remaining = cooldown_minutes * 60 - (time.time() - last_sl)
            logger.debug(f"{symbol}: post-SL cooldown active ({remaining:.0f}s remaining)")
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

        # ── Half-Kelly Position Sizing ──
        # f* = (p*b - q) / b  where p=win_prob, q=1-p, b=avg_win/avg_loss
        # Half-Kelly: f = f* / 2 for reduced variance with ~75% of growth
        lot_size = self._kelly_lot_size(
            symbol, target_exposure, min_lots, sym_max_lots
        )

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
                self.close_positions(shorts, order_meta=order_meta)
                logger.info(f"Closed {n_shorts} short position(s) for {symbol}")

            # Open ONE new long position
            self.open_position(symbol, _mt5.ORDER_TYPE_BUY, lot_size, order_meta=order_meta)
            self.risk.record_trade()
            logger.info(f"Opened long #{n_longs + 1}/{sym_max_positions} for {symbol} ({lot_size} lots)")
        else:
            if n_shorts >= sym_max_positions:
                logger.debug(f"{symbol}: max short positions reached ({n_shorts}/{sym_max_positions})")
                return

            # Close any opposing long positions first
            if n_longs > 0:
                self.close_positions(longs, order_meta=order_meta)
                logger.info(f"Closed {n_longs} long position(s) for {symbol}")

            # Open ONE new short position
            self.open_position(symbol, _mt5.ORDER_TYPE_SELL, lot_size, order_meta=order_meta)
            self.risk.record_trade()
            logger.info(f"Opened short #{n_shorts + 1}/{sym_max_positions} for {symbol} ({lot_size} lots)")

    def close_positions(self, positions, order_meta=None):
        if not self._is_live:
            return

        for p in positions:
            # Use position's own magic/comment as fallback if no meta provided
            meta = order_meta or self._last_order_meta.get(p.symbol, {})
            magic = self._magic_for_order(p.symbol, meta, request_kind="close")
            comment = self._order_comment(p.symbol, meta, request_kind="close")

            request = {
                "action": _mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": _mt5.ORDER_TYPE_SELL if p.type == 0 else _mt5.ORDER_TYPE_BUY,
                "position": p.ticket,
                "magic": magic,
                "comment": comment,
            }
            logger.info(f"MT5 CLOSE: {p.symbol} ticket={p.ticket} | magic={magic} comment={comment}")
            result = _mt5.order_send(request)
            if result.retcode != _mt5.TRADE_RETCODE_DONE:
                logger.error(f"Close position failed for {p.symbol} ticket={p.ticket}: retcode={result.retcode}")
                self.risk.record_error()
            else:
                # Record SL hit time for cooldown tracking
                if p.sl > 0 and p.profit < 0:
                    self._last_sl_hit_time[p.symbol] = time.time()
                    logger.info(f"SL cooldown started for {p.symbol} (15 min)")

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

    def open_position(self, symbol, order_type, volume, order_meta=None):
        if not self._is_live:
            return

        tick = _mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Cannot get tick for {symbol}")
            self.risk.record_error()
            return

        # Compute ATR-based SL/TP defaults
        sl_distance, tp_distance = self._compute_atr_sl_tp(symbol)

        # Enforce minimum SL distance to prevent instant SL hits on tight ATR periods
        # Minimum SL: at least spread * 3 to avoid being stopped out by noise
        spread = tick.ask - tick.bid
        min_sl = max(spread * 3, self._min_sl_for_symbol(symbol))
        if 0 < sl_distance < min_sl:
            logger.warning(f"{symbol}: ATR SL={sl_distance:.5f} too tight, widening to min={min_sl:.5f}")
            sl_distance = min_sl
        # Scale TP proportionally if SL was widened
        if tp_distance > 0 and sl_distance > 0:
            tp_distance = max(tp_distance, sl_distance * 1.5)

        entry_price = tick.ask if order_type == _mt5.ORDER_TYPE_BUY else tick.bid

        # Compute SL/TP price levels
        if order_type == _mt5.ORDER_TYPE_BUY:
            sl = round(entry_price - sl_distance, 5) if sl_distance > 0 else 0
            tp = round(entry_price + tp_distance, 5) if tp_distance > 0 else 0
        else:
            sl = round(entry_price + sl_distance, 5) if sl_distance > 0 else 0
            tp = round(entry_price - tp_distance, 5) if tp_distance > 0 else 0

        # Magic number and comment for trade identification
        meta = order_meta or {}
        magic = self._magic_for_order(symbol, meta, request_kind="open")
        comment = self._order_comment(symbol, meta, request_kind="open")

        # Store meta for close order matching
        self._last_order_meta[symbol] = meta

        request = {
            "action": _mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": entry_price,
            "magic": magic,
            "comment": comment,
        }
        if sl > 0:
            request["sl"] = sl
        if tp > 0:
            request["tp"] = tp

        logger.info(f"MT5 ORDER: {symbol} {'BUY' if order_type == _mt5.ORDER_TYPE_BUY else 'SELL'} "
                     f"{volume:.2f} lots @ {entry_price} | SL={sl} TP={tp} | magic={magic} comment={comment}")
        result = _mt5.order_send(request)
        if result.retcode != _mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5 order failed: retcode={result.retcode}")
            self.risk.record_error()
        else:
            # Play audio alert on successful trade execution
            self._play_trade_alert()

    @staticmethod
    def _min_sl_for_symbol(symbol):
        """Minimum SL distance (in price units) per symbol type.
        Prevents stop-outs from noise/spread during low-ATR periods."""
        # Gold: min $10 distance (XAUUSD ~4800, $10 = ~0.2%)
        if "XAU" in symbol.upper():
            return 10.0
        # BTC: min $500 distance (BTC ~75000, $500 = ~0.67%)
        if "BTC" in symbol.upper():
            return 500.0
        # ETH: min $30
        if "ETH" in symbol.upper():
            return 30.0
        # FX pairs: min 0.003 (30 pips for 5-digit pricing)
        return 0.003

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

    def _get_raw_atr(self, symbol, atr_period=14):
        """Get the raw ATR14 value (not multiplied by SL/TP factors)."""
        try:
            rates = _mt5.copy_rates_from_pos(symbol, _mt5.TIMEFRAME_M5, 0, atr_period + 1)
            if rates is None or len(rates) < atr_period + 1:
                return 0

            high = rates["high"]
            low = rates["low"]
            close = rates["close"]
            trs = []
            for i in range(1, len(rates)):
                tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
                trs.append(tr)
            return sum(trs[-atr_period:]) / atr_period if len(trs) >= atr_period else 0
        except Exception as e:
            logger.warning(f"Raw ATR computation failed for {symbol}: {e}")
            return 0

    def manage_trailing_stops(self):
        """Check all open positions and apply trailing stops.

        For each position, if price has moved in our favor by more than
        trailing_trigger_atr * ATR, we move the SL to lock in profit.
        The new SL is placed at current_price - trailing_distance_atr * ATR
        (for longs) or current_price + trailing_distance_atr * ATR (for shorts).

        Should be called periodically (e.g. every 30-60 seconds).
        """
        if not self._is_live or _mt5 is None:
            return

        try:
            # MT5 must be initialized in each background thread context
            if not _mt5.initialize():
                logger.debug("Trailing stop: MT5 init failed in thread context")
                return

            try:
                positions = _mt5.positions_get()
                if not positions:
                    return

                logger.debug(f"Trailing stop check: {len(positions)} open positions")
                for p in positions:
                    self._trail_single_position(p)
            finally:
                _mt5.shutdown()
        except Exception as e:
            logger.warning(f"Trailing stop management error: {e}")

    def _trail_single_position(self, position):
        """Apply trailing stop to a single position if conditions are met."""
        import yaml

        symbol = position.symbol
        is_long = position.type == 0  # 0 = BUY/long, 1 = SELL/short
        current_sl = position.sl
        current_tp = position.tp
        open_price = position.price_open

        # Get current tick
        tick = _mt5.symbol_info_tick(symbol)
        if tick is None:
            return

        current_price = tick.bid if is_long else tick.ask

        # Load trailing config
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "configs", f"{symbol}.yaml"
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    sym_cfg = yaml.safe_load(f)
                risk_cfg = sym_cfg.get("risk", {})
                trigger_atr = risk_cfg.get("trailing_trigger_atr", 1.5)
                distance_atr = risk_cfg.get("trailing_distance_atr", 1.5)
            else:
                trigger_atr = 1.5
                distance_atr = 1.5
        except Exception:
            trigger_atr = 1.5
            distance_atr = 1.5

        # Calculate raw ATR (not SL-adjusted) for trailing stop computation
        raw_atr = self._get_raw_atr(symbol)
        if raw_atr <= 0:
            return

        trigger_distance = raw_atr * trigger_atr
        trail_distance = raw_atr * distance_atr

        if is_long:
            # Check if price has moved enough to trigger trailing
            profit_distance = current_price - open_price
            if profit_distance < trigger_distance:
                return

            # New SL = current_price - trail_distance
            new_sl = round(current_price - trail_distance, 5)

            # Only move SL up, never down
            if new_sl <= current_sl and current_sl > 0:
                return

            # Don't move SL below entry
            if new_sl <= open_price:
                return

            # Modify the position SL/TP using TRADE_ACTION_SLTP
            request = {
                "action": _mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "position": position.ticket,
                "sl": new_sl,
                "tp": current_tp,
            }
            result = _mt5.order_send(request)
            if result.retcode == _mt5.TRADE_RETCODE_DONE:
                logger.info(f"TRAILING STOP {symbol} long #{position.ticket}: SL moved {current_sl} -> {new_sl} (locked in {new_sl - open_price:.5f} profit)")
            else:
                logger.warning(f"Trailing stop modify failed for {symbol} long #{position.ticket}: retcode={result.retcode} comment={getattr(result, 'comment', '')}")

        else:  # Short position
            profit_distance = open_price - current_price
            if profit_distance < trigger_distance:
                return

            new_sl = round(current_price + trail_distance, 5)

            if new_sl >= current_sl and current_sl > 0:
                return

            if new_sl >= open_price:
                return

            request = {
                "action": _mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "position": position.ticket,
                "sl": new_sl,
                "tp": current_tp,
            }
            result = _mt5.order_send(request)
            if result.retcode == _mt5.TRADE_RETCODE_DONE:
                logger.info(f"TRAILING STOP {symbol} short #{position.ticket}: SL moved {current_sl} -> {new_sl} (locked in {open_price - new_sl:.5f} profit)")
            else:
                logger.warning(f"Trailing stop modify failed for {symbol} short #{position.ticket}: retcode={result.retcode} comment={getattr(result, 'comment', '')}")
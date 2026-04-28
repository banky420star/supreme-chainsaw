"""
MT5 Executor — Trade execution with conditional MT5 import and dry-run mode.
Automatically falls back to DryRunExecutor on Mac/Linux.
Supports multi-position trading: up to N concurrent positions per symbol.
"""
import sys
import os
import json
import time
from datetime import datetime, timezone
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
        self._last_spread_spike_time = {}  # symbol -> timestamp of last spread spike rejection
        self._last_failed_signal_time = {}  # symbol -> timestamp of last failed signal

        # ── Half-Kelly position sizing state ──
        self._kelly_win_rate = {}     # symbol -> recent win rate (0-1)
        self._kelly_avg_win = {}      # symbol -> average winning trade PnL
        self._kelly_avg_loss = {}     # symbol -> average losing trade PnL (positive)
        self._kelly_last_update = {}  # symbol -> timestamp of last stats update

        # ── Cached broker parameters (read once, not per-trade) ──────────────
        self._min_lots = float(os.environ.get("AGI_MIN_LOTS", "0.01"))
        self._default_lot_step = 0.02  # fallback if broker doesn't provide volume_step
        self._mt5_has_calendar = hasattr(_mt5, "calendar_country") if _mt5 else False

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

        # ── Execution log ────────────────────────────────────────────────
        _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._exec_log_path = os.path.join(_base, "logs", "executions.jsonl")
        os.makedirs(os.path.dirname(self._exec_log_path), exist_ok=True)

        # ── Reference to AGIServer for live_armed check (set externally) ──
        self._server_ref = None

    def set_server_ref(self, server):
        """Set reference to AGIServer for live_armed and other runtime checks."""
        self._server_ref = server

    def _preflight_check(self, symbol: str, side: str, lots: float) -> tuple:
        """
        Pre-flight validation before sending any order.
        Returns (allowed: bool, reason: str).
        """
        # 1. Check live mode is armed
        if self._server_ref and hasattr(self._server_ref, "live"):
            if self._server_ref.live and not getattr(self._server_ref, "live_armed", False):
                return False, "live_mode_not_armed"

        # 2. Verify symbol is in allowed list
        if self._server_ref and hasattr(self._server_ref, "symbols"):
            if symbol not in self._server_ref.symbols:
                return False, f"symbol_not_allowed ({symbol})"

        # 2b. Check trading session filter
        session_ok, session_reason = self._check_session_filter(symbol)
        if not session_ok:
            return False, session_reason

        # 3. Check spread under threshold (per-symbol config)
        spread_ok, spread_reason = self._check_spread_guard(symbol)
        if not spread_ok:
            self._last_spread_spike_time[symbol] = time.time()
            return False, spread_reason

        # 3b. Spread spike cooldown: wait 2 min after a spread rejection
        last_spread_spike = self._last_spread_spike_time.get(symbol, 0)
        if last_spread_spike > 0 and (time.time() - last_spread_spike) < 120:
            remaining = 120 - (time.time() - last_spread_spike)
            return False, f"spread_spike_cooldown ({remaining:.0f}s remaining)"

        # 3c. Failed signal cooldown: wait 5 min after a preflight failure
        last_failed = self._last_failed_signal_time.get(symbol, 0)
        if last_failed > 0 and (time.time() - last_failed) < 300:
            remaining = 300 - (time.time() - last_failed)
            return False, f"failed_signal_cooldown ({remaining:.0f}s remaining)"

        # 4. Verify lot size within symbol cap
        try:
            import yaml
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "configs", f"{symbol}.yaml"
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    sym_cfg = yaml.safe_load(f)
                max_lots = sym_cfg.get("risk", {}).get("max_lots", 1.0)
                if lots > max_lots:
                    return False, f"lot_size_exceeds_cap ({lots} > {max_lots})"
        except Exception:
            pass

        # 5. Verify margin is sufficient (live mode only)
        if self._is_live and _mt5 is not None:
            try:
                account = _mt5.account_info()
                if account:
                    # Use MT5's actual margin calculation for the symbol/lot size
                    symbol_info = _mt5.symbol_info(symbol)
                    if symbol_info:
                        # MT5 provides margin_required for 1 lot; scale by actual lots
                        # margin_initial is for 1 lot in the account currency
                        margin_per_lot = getattr(symbol_info, 'margin_initial', 0) or getattr(symbol_info, 'margin_maintenance', 0)
                        if margin_per_lot > 0:
                            required_margin = margin_per_lot * lots
                        else:
                            # Fallback: use trade_mode and contract_size to estimate
                            # For forex with 1:100 leverage, ~$1000 per standard lot
                            # For micro lots (0.01), ~$10 — but broker may offer higher leverage
                            contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
                            leverage_ratio = getattr(account, 'leverage', 100)
                            # Margin = contract_size * lots / leverage
                            required_margin = (contract_size * lots) / leverage_ratio

                        if account.margin_free < required_margin:
                            return False, f"insufficient_margin (free={account.margin_free:.2f}, required={required_margin:.2f})"
            except Exception:
                pass

        return True, "ok"

    def _check_session_filter(self, symbol: str) -> tuple:
        """Check if current UTC hour falls within allowed trading sessions.

        Sessions (UTC):
        - Asian: 00:00-08:00
        - London: 07:00-16:00
        - New York: 12:00-21:00

        Returns (ok: bool, reason: str).
        """
        try:
            import yaml
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "configs", f"{symbol}.yaml"
            )
            if not os.path.exists(config_path):
                return True, "ok"  # No config = all sessions allowed

            with open(config_path, "r") as f:
                sym_cfg = yaml.safe_load(f) or {}

            sessions = sym_cfg.get("trading_sessions", {})
            if not sessions:
                return True, "ok"  # No session filter = all allowed

            from datetime import datetime, timezone
            utc_hour = datetime.now(timezone.utc).hour

            # Determine which sessions COVER this hour (regardless of enabled/disabled)
            # Overlaps: 0-8=Asian, 7-16=London, 12-21=New York
            covering_sessions = []
            if 0 <= utc_hour < 8:
                covering_sessions.append("asian")
            if 7 <= utc_hour < 16:
                covering_sessions.append("london")
            if 12 <= utc_hour < 21:
                covering_sessions.append("new_york")

            # Hours 21-24 UTC: no session covers — allow trading (edge case)
            if not covering_sessions:
                return True, "ok"

            # Check if at least one covering session is enabled
            for session in covering_sessions:
                if sessions.get(session, True):
                    return True, "ok"

            # All covering sessions are disabled — block trading
            return False, f"outside_trading_session (utc_hour={utc_hour}, covering={covering_sessions})"

        except Exception as e:
            logger.debug(f"Session filter check failed for {symbol}: {e}")
            return True, "ok"

    def _check_spread_guard(self, symbol: str) -> tuple:
        """
        Check if current spread is within the per-symbol threshold.
        Returns (ok: bool, reason: str).
        """
        max_spread_bps = 50  # default
        try:
            import yaml
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "configs", f"{symbol}.yaml"
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    sym_cfg = yaml.safe_load(f)
                max_spread_bps = sym_cfg.get("risk", {}).get("max_spread_bps", 50)
        except Exception:
            pass

        if not self._is_live or _mt5 is None:
            return True, "ok"

        try:
            tick = _mt5.symbol_info_tick(symbol)
            if tick is None:
                return False, f"no_tick_data ({symbol})"
            spread = tick.ask - tick.bid
            # For FX: spread in points (5th decimal for 5-digit brokers)
            # For XAU/BTC: spread in raw price
            point = _mt5.symbol_info(symbol)
            if point:
                spread_bps = (spread / point.point) if point.point > 0 else 0
                if spread_bps > max_spread_bps:
                    return False, f"spread_too_wide ({spread_bps:.1f} > {max_spread_bps} bps)"
        except Exception as e:
            logger.warning(f"Spread guard check failed for {symbol}: {e}")

        return True, "ok"

    def _log_execution(self, record: dict):
        """Append execution intent record to logs/executions.jsonl."""
        try:
            with open(self._exec_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write execution log: {e}")

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

    def compute_risk_adjusted_lots(self, symbol, exposure, confidence_scale=1.0):
        """Compute lots based on risk-per-trade percentage and ATR stop distance.

        Formula: lots = (equity * risk_pct / 100) / (SL_distance * pip_value)
        This scales automatically from $50 to $250K+.

        Falls back to Kelly sizing if ATR is unavailable.
        """
        risk_pct = getattr(self.risk, 'risk_per_trade_pct', 1.0)
        equity = getattr(self.risk, '_current_equity', 0)
        if equity <= 0:
            equity = 50.0

        # Get ATR-based SL distance
        atr = self._get_raw_atr(symbol)
        if atr <= 0:
            # Fall back to Kelly
            min_lots = self._min_lots
            sym_max_lots = self._get_symbol_max_lots(symbol)
            return self._kelly_lot_size(symbol, exposure, min_lots, sym_max_lots)

        # Load per-symbol ATR multiplier for SL
        sl_mult = self._get_symbol_sl_mult(symbol)
        sl_distance = atr * sl_mult

        # Dollar risk for this trade
        max_risk_dollars = equity * risk_pct / 100.0

        # Get pip value from MT5 tick data
        pip_value = self._get_tick_pip_value(symbol)
        if pip_value <= 0:
            pip_value = self._pip_value_per_lot(symbol)

        # Lots = risk_dollars / (sl_distance_in_pips * pip_value_per_pip_per_lot)
        # Convert SL distance to pips, then multiply by pip value
        min_lots = self._min_lots
        tick_size = self._get_tick_size(symbol)

        # For small accounts: cap SL distance to what equity can afford
        # (same logic as open_position — prevents gold/BTC ATR SLs from blocking trades)
        if equity < 100 and sl_distance > 0:
            max_sl_equity_pct_local = 15.0
            max_risk_dollars_local = equity * max_sl_equity_pct_local / 100.0
            if pip_value > 0 and tick_size > 0:
                max_sl_dist = max_risk_dollars_local / (min_lots * pip_value / tick_size) if min_lots > 0 else sl_distance
                min_sl_floor = max(0.00005 * 2, self._min_sl_for_symbol(symbol) * 0.04)
                if max_sl_dist > min_sl_floor and sl_distance > max_sl_dist:
                    sl_distance = max_sl_dist

        if tick_size > 0:
            sl_pips = sl_distance / tick_size
            lots = max_risk_dollars / (sl_pips * pip_value)
        else:
            lots = min_lots  # safe fallback

        # Scale by confidence
        lots *= confidence_scale

        # Clamp to per-symbol max
        sym_max_lots = self._get_symbol_max_lots(symbol)
        lots = max(min_lots, min(lots, sym_max_lots))

        # ── Max SL equity cap: no single trade should risk more than X% of equity ──
        max_sl_equity_pct = getattr(self.risk, 'max_sl_equity_pct', 10.0)
        # For small accounts (<$100), raise the cap to 15% to allow trading
        if equity < 100:
            max_sl_equity_pct = max(max_sl_equity_pct, 15.0)
        max_sl_dollars = equity * max_sl_equity_pct / 100.0
        if tick_size > 0 and pip_value > 0 and lots > 0:
            actual_risk_dollars = lots * sl_pips * pip_value
            if actual_risk_dollars > max_sl_dollars * 1.01 and actual_risk_dollars > 0:
                # Calculate the safe lot size for this equity cap
                safe_lots = max_sl_dollars / (sl_pips * pip_value)
                if safe_lots < min_lots:
                    # Even minimum lots exceeds the equity risk cap — SKIP this trade entirely
                    logger.warning(
                        f"ATR sizing {symbol}: SKIP — min_lots {min_lots} risks "
                        f"${min_lots * sl_pips * pip_value:.2f} > {max_sl_equity_pct}% equity "
                        f"(${max_sl_dollars:.2f}). Safe lots={safe_lots:.4f}. "
                        f"Account too small for this symbol."
                    )
                    return 0.0
                lots = safe_lots
                lots = min(lots, sym_max_lots)
                logger.info(
                    f"ATR sizing {symbol}: SL equity cap triggered — "
                    f"risk ${actual_risk_dollars:.2f} > {max_sl_equity_pct}% (${max_sl_dollars:.2f}), "
                    f"reduced to {lots:.2f} lots"
                )

        # Round to lot step (read from broker if available)
        lot_step = self._get_lot_step(symbol)
        lots = round(lots / lot_step) * lot_step
        lots = max(min_lots, min(lots, sym_max_lots))

        logger.info(
            f"ATR sizing {symbol}: equity=${equity:.2f} risk_pct={risk_pct}% "
            f"atr={atr:.5f} sl_dist={sl_distance:.5f} risk=${max_risk_dollars:.2f} "
            f"-> {lots:.2f} lots"
        )
        return lots

    def _get_symbol_max_lots(self, symbol: str) -> float:
        """Get max lots from per-symbol config."""
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "configs", f"{symbol}.yaml"
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    sym_cfg = yaml.safe_load(f)
                return float(sym_cfg.get("risk", {}).get("max_lots", 1.0))
        except Exception:
            pass
        return 1.0

    def _get_lot_step(self, symbol: str) -> float:
        """Get lot step from broker symbol info, fallback to default."""
        try:
            if self._is_live:
                info = _mt5.symbol_info(symbol)
                if info and getattr(info, "volume_step", 0) > 0:
                    return float(info.volume_step)
        except Exception:
            pass
        return self._default_lot_step

    def _get_symbol_sl_mult(self, symbol: str) -> float:
        """Get SL ATR multiplier from per-symbol config."""
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "configs", f"{symbol}.yaml"
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    sym_cfg = yaml.safe_load(f)
                return float(sym_cfg.get("risk", {}).get("sl_atr_mult", 2.0))
        except Exception:
            pass
        return 2.0

    def _get_tick_pip_value(self, symbol: str) -> float:
        """Get tick value per lot from MT5 symbol info."""
        if not self._is_live or _mt5 is None:
            return 0.0
        try:
            info = _mt5.symbol_info(symbol)
            if info is None:
                return 0.0
            tick_value = getattr(info, 'trade_tick_value', 0)
            return float(tick_value) if tick_value else 0.0
        except Exception:
            return 0.0

    def _get_tick_size(self, symbol: str) -> float:
        """Get tick size from MT5 symbol info."""
        if not self._is_live or _mt5 is None:
            return 0.0
        try:
            info = _mt5.symbol_info(symbol)
            if info is None:
                return 0.0
            tick_size = getattr(info, 'trade_tick_size', 0)
            return float(tick_size) if tick_size else 0.0
        except Exception:
            return 0.0

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
        """Calculate lot size using Full Kelly criterion.

        Kelly fraction: f* = (p*b - q) / b
        Where: p = win probability, q = 1-p, b = avg_win / avg_loss
        Full Kelly: use the entire Kelly fraction for maximum growth.

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

        # Full Kelly (aggressive sizing for maximum growth)
        kelly_used = kelly_full

        # Scale by conviction (|exposure| as signal strength)
        # exposure is typically 0.001-0.05, normalize to 0.3-1.0 range
        conviction = min(1.0, max(0.3, abs(exposure) * 20))

        # Risk budget: fraction of account we're willing to risk per trade
        # Use BALANCE (realized) not equity (includes floating P&L) for sizing.
        # Floating profits from one symbol should NOT inflate sizing on others.
        # E.g. XAUUSDm up $200 floating -> Kelly shouldn't size EURUSDm at 1.0 lots
        balance = getattr(self.risk, "_mt5_balance", None)
        if balance is None or balance <= 0:
            # Fall back to equity only if balance unavailable
            balance = getattr(self.risk, "_current_equity", None)
        if balance is None or balance <= 0:
            balance = 50.0  # fallback for dry-run or missing account info

        # Compound growth: scale ramps up as balance grows
        # Under $50: very conservative (0.3x) to protect tiny accounts
        # $50-$200: linear ramp from 0.3x to 0.8x
        # $200-$1000: linear ramp from 0.8x to 1.0x
        # Above $1000: full Kelly (1.0x)
        if balance < 50:
            equity_scale = 0.3
        elif balance < 200:
            equity_scale = 0.3 + 0.5 * ((balance - 50) / 150)  # 0.3 to 0.8
        elif balance < 1000:
            equity_scale = 0.8 + 0.2 * ((balance - 200) / 800)  # 0.8 to 1.0
        else:
            equity_scale = 1.0
        kelly_used = kelly_used * equity_scale

        risk_pct = float(os.environ.get("AGI_RISK_PERCENT", "2.0")) / 100.0
        risk_budget = balance * risk_pct * kelly_used * conviction

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

        # Start from Kelly-risk-derived lot size
        lot_size = lots_from_risk

        # Hard cap: max risk per trade = max_sl_equity_pct% of balance (regardless of Kelly)
        # This prevents disasters like 1.0 lots on a $40 account
        max_sl_equity_pct = getattr(self.risk, 'max_sl_equity_pct', 10.0)
        if balance < 100:
            max_sl_equity_pct = max(max_sl_equity_pct, 15.0)
        max_risk_dollars = balance * max_sl_equity_pct / 100.0
        if avg_loss > 0 and lot_size > 0:
            max_lots_by_risk = max_risk_dollars / avg_loss
            lot_size = min(lot_size, max_lots_by_risk)

        # Apply broker minimum and maximum
        lot_size = max(min_lots, min(lot_size, max_lots))

        # Round to broker lot step
        lot_step = self._get_lot_step(symbol)
        lot_size = round(lot_size / lot_step) * lot_step
        lot_size = max(min_lots, min(lot_size, max_lots))

        logger.info(
            f"Kelly sizing {symbol}: f*={kelly_full:.3f} used={kelly_used:.3f} "
            f"conviction={conviction:.2f} balance=${balance:.2f} scale={equity_scale:.2f} "
            f"risk_budget=${risk_budget:.2f} max_risk=${max_risk_dollars:.2f} -> {lot_size:.2f} lots"
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

            if not self._mt5_has_calendar:
                return False
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
            logger.debug(f"News blackout check failed for {symbol}: {e}")
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
            self._log_execution({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol, "side": "BUY" if target_exposure > 0 else "SELL",
                "lot_size": 0, "allowed": False, "reason": "news_blackout_active",
            })
            return

        # ── Pre-flight checks ────────────────────────────────────────────
        # Load per-symbol risk config FIRST so preflight uses the right caps
        sym_max_lots = max_lots
        sym_max_positions = max_positions_per_symbol
        sym_min_lots = self._min_lots

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
                sym_min_lots = float(risk_cfg.get("min_lots", self._min_lots))
        except Exception:
            pass

        # ── Per-symbol minimum equity check ─────────────────────────────────
        # Reject trades on symbols where even the minimum lot size would risk
        # more than max_sl_equity_pct of equity. E.g. XAUUSDm 0.01 lots risks $18+
        # on a $22 account — 80%+ of equity, which exceeds the 10% cap.
        min_lots = sym_min_lots
        equity = getattr(self.risk, "_current_equity", None)
        if equity is None or equity <= 0:
            equity = 50.0
        max_sl_equity_pct = getattr(self.risk, 'max_sl_equity_pct', 10.0)
        # For small accounts (<$100), raise the cap to 15% to allow trading
        if equity < 100:
            max_sl_equity_pct = max(max_sl_equity_pct, 15.0)
        max_sl_dollars = equity * max_sl_equity_pct / 100.0

        # Calculate SL distance for this symbol to estimate min risk
        sl_mult = self._get_symbol_sl_mult(symbol)
        raw_atr = self._get_raw_atr(symbol)
        if raw_atr > 0 and max_sl_dollars > 0:
            sl_distance = raw_atr * sl_mult
            # Apply same min SL floor as open_position to avoid passing trades that will be blocked
            if equity < 100:
                min_sl_floor = max(0.00005 * 2, self._min_sl_for_symbol(symbol) * 0.04)
            else:
                min_sl_floor = max(0.00005 * 3, self._min_sl_for_symbol(symbol))
            if sl_distance < min_sl_floor:
                sl_distance = min_sl_floor
            # For small accounts: cap SL distance to what equity can afford
            if equity < 100 and sl_distance > min_sl_floor:
                tick_sz = self._get_tick_size(symbol)
                pip_val = self._get_tick_pip_value(symbol) or self._pip_value_per_lot(symbol)
                if tick_sz > 0 and pip_val > 0 and min_lots > 0:
                    max_sl_dist = max_sl_dollars / (min_lots * pip_val / tick_sz)
                    if sl_distance > max_sl_dist and max_sl_dist > min_sl_floor:
                        sl_distance = max_sl_dist
            pip_value = self._get_tick_pip_value(symbol) or self._pip_value_per_lot(symbol)
            tick_size = self._get_tick_size(symbol)
            if pip_value > 0 and tick_size > 0:
                sl_pips = sl_distance / tick_size
                min_risk = min_lots * sl_pips * pip_value
                if min_risk > max_sl_dollars * 1.01:  # 1% buffer for rounding
                    logger.warning(
                        f"{symbol}: SKIP — min_lots {min_lots} risks ${min_risk:.2f} > "
                        f"{max_sl_equity_pct}% equity (${max_sl_dollars:.2f}). "
                        f"Account too small for this symbol."
                    )
                    self._log_execution({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "symbol": symbol, "side": "BUY" if target_exposure > 0 else "SELL",
                        "lot_size": 0, "allowed": False,
                        "reason": f"equity_too_small_for_symbol (min_risk=${min_risk:.2f} > {max_sl_equity_pct}%=${max_sl_dollars:.2f})",
                    })
                    return

        # For very small accounts (< $50), limit to 1 position per symbol to prevent overexposure
        # Above $50, allow up to config max (typically 3)
        small_account = equity < 50
        if small_account:
            sym_max_positions = 1

        # Apply small account caps AFTER loading config so they don't get clobbered
        if small_account:
            sym_max_positions = 1
            sym_max_lots = min(sym_max_lots, self._min_lots)

        direction = "BUY" if target_exposure > 0 else "SELL"
        allowed, preflight_reason = self._preflight_check(
            symbol, direction, sym_max_lots
        )
        if not allowed:
            logger.warning(f"{symbol}: preflight check FAILED — {preflight_reason}")
            self._last_failed_signal_time[symbol] = time.time()
            self._log_execution({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol, "side": direction,
                "lot_size": 0, "allowed": False, "reason": preflight_reason,
            })
            return

        min_lots = self._min_lots

        # ── ATR-Based Risk-Adjusted Sizing (primary) ──
        # Uses risk_per_trade_pct from risk engine + ATR stop distance
        # Falls back to Kelly criterion if ATR unavailable
        lot_size = self.compute_risk_adjusted_lots(symbol, target_exposure)

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
        hedging_enabled = os.environ.get("AGI_HEDGING_ENABLED", "true").lower() == "true"

        if is_buy:
            # If we already have long positions, don't add more unless under the limit
            # and the existing positions are profitable (avoid doubling down on losers)
            if n_longs >= sym_max_positions:
                logger.debug(f"{symbol}: max long positions reached ({n_longs}/{sym_max_positions})")
                return

            # Close opposing short positions ONLY if hedging is disabled
            if not hedging_enabled and n_shorts > 0:
                self.close_positions(shorts, order_meta=order_meta)
                logger.info(f"Closed {n_shorts} short position(s) for {symbol}")

            # Open ONE new long position
            opened = self.open_position(symbol, _mt5.ORDER_TYPE_BUY, lot_size, order_meta=order_meta)
            if opened:
                self.risk.record_trade()
                logger.info(f"Opened long #{n_longs + 1}/{sym_max_positions} for {symbol} ({lot_size} lots)")
                self._log_execution({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": symbol, "side": "BUY", "lot_size": lot_size,
                    "allowed": True, "reason": "ok",
                    "magic": self._magic_for_order(symbol, order_meta or {}, request_kind="open"),
                    "order_meta": order_meta,
                })
        else:
            if n_shorts >= sym_max_positions:
                logger.debug(f"{symbol}: max short positions reached ({n_shorts}/{sym_max_positions})")
                return

            # Close opposing long positions ONLY if hedging is disabled
            if not hedging_enabled and n_longs > 0:
                self.close_positions(longs, order_meta=order_meta)
                logger.info(f"Closed {n_longs} long position(s) for {symbol}")

            # Open ONE new short position
            opened = self.open_position(symbol, _mt5.ORDER_TYPE_SELL, lot_size, order_meta=order_meta)
            if opened:
                self.risk.record_trade()
                logger.info(f"Opened short #{n_shorts + 1}/{sym_max_positions} for {symbol} ({lot_size} lots)")
                self._log_execution({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": symbol, "side": "SELL", "lot_size": lot_size,
                    "allowed": True, "reason": "ok",
                    "magic": self._magic_for_order(symbol, order_meta or {}, request_kind="open"),
                    "order_meta": order_meta,
                })

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
                # Only critical if retcode indicates a real problem, not market-closed or margin
                critical = result.retcode not in (10018, 10019, 10020, 10021, 10030, 13108)
                self.risk.record_error(critical=critical)
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
        """Open a position. Returns True on success, False on abort/failure, None when not live."""
        if not self._is_live:
            return None

        tick = _mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Cannot get tick for {symbol}")
            self.risk.record_error(critical=False)  # Non-critical: market data issue
            return False

        # Compute ATR-based SL/TP defaults
        sl_distance, tp_distance = self._compute_atr_sl_tp(symbol)

        # Enforce minimum SL distance to prevent instant SL hits on tight ATR periods
        # Minimum SL: at least spread * 3 to avoid being stopped out by noise
        # For small accounts (<$100), use a tighter floor (spread * 2) to allow trading
        spread = tick.ask - tick.bid
        equity = getattr(self.risk, "_current_equity", 0) or 50.0
        if equity < 100:
            # Small accounts: use tighter SL to allow trading
            # FX: 0.003*0.33=0.001 (~10 pips), Gold: $50*0.04=$2, BTC: $500*0.04=$20
            min_sl = max(spread * 2, self._min_sl_for_symbol(symbol) * 0.04)
        else:
            min_sl = max(spread * 3, self._min_sl_for_symbol(symbol))
        if 0 < sl_distance < min_sl:
            logger.warning(f"{symbol}: ATR SL={sl_distance:.5f} too tight, widening to min={min_sl:.5f}")
            sl_distance = min_sl

        # For small accounts (<$100): cap SL distance to what equity can afford
        # This prevents gold/BTC ATR-based SLs ($20-500) from exceeding risk cap
        if equity < 100 and sl_distance > min_sl:
            max_sl_equity_pct_local = 15.0  # same as the cap we use below
            max_risk_dollars = equity * max_sl_equity_pct_local / 100.0
            tick_sz = self._get_tick_size(symbol)
            pip_val = self._get_tick_pip_value(symbol) or self._pip_value_per_lot(symbol)
            if tick_sz > 0 and pip_val > 0 and volume > 0:
                max_sl_distance = max_risk_dollars / (volume * pip_val / tick_sz)
                if sl_distance > max_sl_distance and max_sl_distance > min_sl:
                    logger.info(f"{symbol}: Small-account SL cap: ${sl_distance:.2f} -> ${max_sl_distance:.2f} "
                                f"(max risk ${max_risk_dollars:.2f} = {max_sl_equity_pct_local}% of ${equity:.2f})")
                    sl_distance = max_sl_distance

        # Scale TP proportionally if SL was adjusted
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

        # ── Final safety: cap SL risk at max_sl_equity_pct% of equity ──
        # For small accounts (<$100), raise the cap to 15% to allow trading
        max_sl_equity_pct = getattr(self.risk, 'max_sl_equity_pct', 10.0)
        if equity < 100:
            max_sl_equity_pct = max(max_sl_equity_pct, 15.0)
        equity = getattr(self.risk, '_current_equity', 0) or 50.0
        max_sl_dollars = equity * max_sl_equity_pct / 100.0
        if sl > 0 and sl_distance > 0:
            pip_val = self._get_tick_pip_value(symbol) or self._pip_value_per_lot(symbol)
            tick_sz = self._get_tick_size(symbol)
            if pip_val > 0 and tick_sz > 0:
                sl_pips = sl_distance / tick_sz
                actual_risk = volume * sl_pips * pip_val
                if actual_risk > max_sl_dollars * 1.01:  # 1% buffer for rounding
                    # Calculate safe volume
                    safe_volume = max_sl_dollars / (sl_pips * pip_val)
                    min_lots = self._min_lots
                    if safe_volume < min_lots:
                        # Even minimum lots exceeds equity risk cap — ABORT this trade
                        logger.warning(
                            f"SL equity cap ABORT: {symbol} min_lots {min_lots} risks "
                            f"${min_lots * sl_pips * pip_val:.2f} > {max_sl_equity_pct}% equity "
                            f"(${max_sl_dollars:.2f}). Safe vol={safe_volume:.4f}. "
                            f"Account too small for this symbol."
                        )
                        self.risk.record_error(critical=False)
                        return False
                    lot_step = self._get_lot_step(symbol)
                    safe_volume = round(safe_volume / lot_step) * lot_step
                    # DO NOT floor safe_volume back to min_lots — that defeats the equity cap
                    # If safe_volume rounded down to 0, abort instead
                    if safe_volume < lot_step:
                        logger.warning(
                            f"SL equity cap: {symbol} safe_volume {safe_volume:.4f} < lot_step {lot_step}, ABORT"
                        )
                        return False
                    logger.warning(
                        f"SL equity cap: {symbol} risk ${actual_risk:.2f} > {max_sl_equity_pct}% (${max_sl_dollars:.2f}), "
                        f"reduced volume {volume:.2f} -> {safe_volume:.2f}"
                    )
                    volume = safe_volume

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
            # Only critical for unexpected errors. Common non-critical retcodes:
            # 10018=market_closed, 10019=no_prices, 10030=invalid_volume
            # 10020=no_quote, 10021=requote, 13108=disabled
            critical = result.retcode not in (10018, 10019, 10020, 10021, 10030, 13108)
            self.risk.record_error(critical=critical)
            return False
        else:
            # Play audio alert on successful trade execution
            self._play_trade_alert()
            return True

    @staticmethod
    def _min_sl_for_symbol(symbol):
        """Minimum SL distance (in price units) per symbol type.
        Prevents stop-outs from noise/spread during low-ATR periods.
        These are BASE values — small accounts use a fraction via open_position()."""
        # Gold: base $50, but small accounts use $2 via 0.04x multiplier
        if "XAU" in symbol.upper():
            return 50.0
        # BTC: base $500, but small accounts use $20 via 0.04x multiplier
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
"""
Risk Engine — Portfolio risk management with percentage-of-equity limits.

Enforces hard account protections:
- Daily loss %, hourly loss %, daily trade count
- Max drawdown % auto-halt
- Max open positions (total and per-symbol)
- Margin call protection (% of equity)
- Consecutive error kill switch
- All limits loaded from config.yaml risk section

Scales automatically from $50 to $250K+ — dollar limits are computed
from equity each cycle, so they grow/shrink with the account.
"""
import os
import sys
import yaml
from collections import deque
from datetime import datetime
from loguru import logger


class RiskEngine:
    def __init__(self):
        cfg = {}
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.yaml"
        )
        try:
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"config.yaml not found at {config_path} — using defaults.")
        except Exception as e:
            logger.warning(f"Failed to read config.yaml: {e} — using defaults.")

        risk_cfg = cfg.get("risk", {})
        # ── Percentage-based loss limits (scales with equity) ──
        self.max_daily_loss_pct = float(risk_cfg.get("max_daily_loss_pct", 3.0))
        self.max_hourly_loss_pct = float(risk_cfg.get("max_hourly_loss_pct", 1.0))
        self.risk_per_trade_pct = float(risk_cfg.get("risk_per_trade_pct", 1.0))
        self.margin_min_pct = float(risk_cfg.get("margin_min_pct", 2.0))

        # ── Legacy dollar limits (fallback if pct not set) ──
        self._legacy_daily_loss = float(risk_cfg.get("max_daily_loss", 0))
        self._legacy_hourly_loss = float(risk_cfg.get("max_hourly_loss", 0))

        # ── Fixed limits (not equity-dependent) ──
        self.max_daily_trades = int(risk_cfg.get("max_daily_trades", 200))
        self.max_lots = float(risk_cfg.get("max_lots", 2.0))
        self.max_drawdown_pct = float(risk_cfg.get("max_drawdown_pct", 25.0))
        self.max_open_positions = int(risk_cfg.get("max_open_positions", 8))
        self.max_positions_per_symbol = int(risk_cfg.get("max_positions_per_symbol", 2))
        self.max_spread_bps = int(risk_cfg.get("max_spread_bps", 50))
        self.max_slippage_points = int(risk_cfg.get("max_slippage_points", 10))
        self.max_sl_equity_pct = float(risk_cfg.get("max_sl_equity_pct", 10.0))

        # ── Portfolio risk limits ──
        self.max_portfolio_sl_pct = float(risk_cfg.get("max_portfolio_sl_pct", 30.0))  # total SL risk across all positions
        self.max_directional_pct = float(risk_cfg.get("max_directional_pct", 70.0))  # max % of positions in same direction

        self.realized_pnl_today = 0.0
        self.daily_trades = 0
        self.halt = False
        self.error_count = 0
        self._halt_reason = ""

        # ── Hourly loss tracking ──────────────────────────────────────
        self._hourly_pnl = deque()  # (timestamp, pnl) pairs for last hour
        self._last_hourly_reset = datetime.utcnow()

        # ── Bootstrap equity from MT5 or AGI_START_EQUITY ─────────────
        initial_equity = self._bootstrap_equity()
        self._peak_equity = initial_equity
        self._current_equity = initial_equity

        # Equity history for performance charts (capped at 300 points)
        self._equity_history = []
        self._pnl_history = []

        logger.info(
            f"RiskEngine initialized: max_daily_loss={self.max_daily_loss_pct}% "
            f"max_hourly_loss={self.max_hourly_loss_pct}% "
            f"risk_per_trade={self.risk_per_trade_pct}% "
            f"margin_min={self.margin_min_pct}% "
            f"max_trades={self.max_daily_trades} max_lots={self.max_lots} "
            f"max_dd={self.max_drawdown_pct}% max_positions={self.max_open_positions} "
            f"max_per_symbol={self.max_positions_per_symbol} "
            f"initial_equity=${initial_equity:.2f}"
        )

    # ── Dynamic dollar limits (computed from current equity) ────────────

    @property
    def max_daily_loss(self) -> float:
        """Max daily loss in dollars, computed from equity percentage."""
        if self._legacy_daily_loss > 0 and self.max_daily_loss_pct <= 0:
            return self._legacy_daily_loss
        return abs(self.max_daily_loss_pct / 100.0 * self._current_equity)

    @property
    def max_hourly_loss(self) -> float:
        """Max hourly loss in dollars, computed from equity percentage."""
        if self._legacy_hourly_loss > 0 and self.max_hourly_loss_pct <= 0:
            return self._legacy_hourly_loss
        return abs(self.max_hourly_loss_pct / 100.0 * self._current_equity)

    @property
    def margin_min_dollars(self) -> float:
        """Minimum free margin in dollars, computed from equity percentage."""
        return abs(self.margin_min_pct / 100.0 * self._current_equity)

    @staticmethod
    def _bootstrap_equity() -> float:
        """Read initial equity from MT5 account (Windows) or AGI_START_EQUITY env var."""
        # Try MT5 first on Windows
        if sys.platform == "win32":
            try:
                import MetaTrader5 as mt5
                if mt5.initialize():
                    info = mt5.account_info()
                    if info is not None and info.equity > 0:
                        logger.info(f"RiskEngine: initial equity from MT5 = ${info.equity:.2f}")
                        return float(info.equity)
            except Exception as e:
                logger.debug(f"RiskEngine: MT5 equity read failed ({e}), falling back to env var")

        # Fallback: env var
        env_eq = os.environ.get("AGI_START_EQUITY", "0")
        try:
            val = float(env_eq)
            if val > 0:
                logger.info(f"RiskEngine: initial equity from AGI_START_EQUITY = ${val:.2f}")
                return val
        except ValueError:
            pass

        logger.warning("RiskEngine: no initial equity source — defaulting to 0.0")
        return 0.0

    @property
    def current_dd(self) -> float:
        """Current drawdown as a percentage (0-100)."""
        if self._peak_equity <= 0:
            return 0.0
        return max(0.0, (self._peak_equity - self._current_equity) / self._peak_equity * 100.0)

    def update_equity(self, equity: float):
        """Update equity tracking for drawdown calculation."""
        self._current_equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity
        # Store history for charts
        self._equity_history.append(float(equity))
        if len(self._equity_history) > 300:
            self._equity_history = self._equity_history[-300:]
        pnl = getattr(self, "_mt5_profit", 0.0) or 0.0
        self._pnl_history.append(float(pnl))
        if len(self._pnl_history) > 300:
            self._pnl_history = self._pnl_history[-300:]

    def reset_daily(self):
        self.realized_pnl_today = 0.0
        self.daily_trades = 0
        self.error_count = 0
        self._hourly_pnl.clear()
        self._last_hourly_reset = datetime.utcnow()
        if not self.halt or "daily_loss" not in self._halt_reason:
            self.halt = False
            self._halt_reason = ""

    def _check_hourly_reset(self):
        """Reset hourly PnL tracking at the top of each hour."""
        now = datetime.utcnow()
        if now.hour != self._last_hourly_reset.hour or (
            now.day != self._last_hourly_reset.day
        ):
            self._hourly_pnl.clear()
            self._last_hourly_reset = now

    def reset_peak_equity(self):
        """Reset peak equity to current equity (e.g. after cash withdrawal)."""
        self._peak_equity = max(self._current_equity, 0.01)
        logger.info(f"RiskEngine: peak equity reset to {self._peak_equity:.2f}")

    def record_trade(self):
        self.daily_trades += 1
        # Reset consecutive error count on any successful trade
        self.error_count = 0

    def record_pnl(self, pnl: float):
        daily_limit = self.max_daily_loss  # property: pct of equity
        hourly_limit = self.max_hourly_loss  # property: pct of equity
        self.realized_pnl_today += pnl
        if self.realized_pnl_today <= -daily_limit:
            self.halt = True
            self._halt_reason = "daily_loss"
            logger.error(f"🛑 KILL SWITCH: Daily loss ${self.realized_pnl_today:.2f} exceeded limit ${daily_limit:.2f} ({self.max_daily_loss_pct}% of ${self._current_equity:.2f})")

        # Track hourly PnL
        self._check_hourly_reset()
        self._hourly_pnl.append((datetime.utcnow(), pnl))
        hourly_total = sum(p for _, p in self._hourly_pnl)
        if hourly_total <= -hourly_limit:
            self.halt = True
            self._halt_reason = "hourly_loss"
            logger.error(f"🛑 KILL SWITCH: Hourly loss ${hourly_total:.2f} exceeded limit ${hourly_limit:.2f} ({self.max_hourly_loss_pct}% of ${self._current_equity:.2f})")

    def record_error(self, critical: bool = True):
        """Record an error. Only critical errors increment the counter for kill switch.
        Non-critical errors (market closed, insufficient margin, etc.) are logged but don't trigger halt.
        Consecutive error counter resets to 0 on any successful trade (record_trade).
        """
        if critical:
            self.error_count += 1
            if self.error_count >= 3:
                self.halt = True
                self._halt_reason = "consecutive_errors"
                logger.error(f"🛑 KILL SWITCH: {self.error_count} consecutive errors")
        # Always log the error
        logger.warning(f"RiskEngine: error recorded (critical={critical}, count={self.error_count})")

    def can_trade(self, symbol: str = None) -> bool:
        """Check if a trade is allowed.

        Enforces:
        - Global halt (daily loss, hourly loss, drawdown, consecutive errors)
        - Auto-recovery: drawdown halt lifts when equity recovers below threshold
        - Daily trade limit
        - Max drawdown % auto-halt
        - Max open positions (total and per-symbol)
        - Margin call protection (% of equity)
        """
        # Auto-recovery: if halted due to drawdown, check if equity recovered
        if self.halt and self._halt_reason == "max_drawdown":
            recovery_threshold = self.max_drawdown_pct * 0.8  # resume at 80% of limit
            if self.current_dd < recovery_threshold:
                self.halt = False
                self._halt_reason = ""
                logger.success(
                    f"✅ AUTO-RECOVERY: Drawdown {self.current_dd:.1f}% < {recovery_threshold:.1f}% "
                    f"(recovery threshold) — trading resumed"
                )
            else:
                logger.debug(f"RiskEngine: trade blocked — halt (drawdown {self.current_dd:.1f}% >= recovery {recovery_threshold:.1f}%)")
                return False

        if self.halt:
            logger.debug(f"RiskEngine: trade blocked — halt ({self._halt_reason})")
            return False
        if self.daily_trades >= self.max_daily_trades:
            logger.debug(f"RiskEngine: trade blocked — daily trade limit ({self.daily_trades}/{self.max_daily_trades})")
            return False

        # Max drawdown % auto-halt
        if self.max_drawdown_pct > 0 and self.current_dd >= self.max_drawdown_pct:
            self.halt = True
            self._halt_reason = "max_drawdown"
            logger.error(
                f"🛑 KILL SWITCH: Drawdown {self.current_dd:.1f}% >= {self.max_drawdown_pct}% — halting, will auto-resume below {self.max_drawdown_pct * 0.8:.1f}%"
            )
            return False

        # Max open positions total
        open_positions = self._get_open_positions_count()
        if open_positions >= self.max_open_positions:
            logger.debug(f"RiskEngine: trade blocked — max positions ({open_positions}/{self.max_open_positions})")
            return False

        # Max open positions per symbol
        if symbol and self.max_positions_per_symbol > 0:
            symbol_positions = self._get_symbol_positions_count(symbol)
            if symbol_positions >= self.max_positions_per_symbol:
                logger.debug(f"RiskEngine: trade blocked — {symbol} max positions ({symbol_positions}/{self.max_positions_per_symbol})")
                return False

        # Margin call protection: if free margin is dangerously low, stop trading
        free_margin = getattr(self, "_mt5_free_margin", None)
        margin_min = self.margin_min_dollars
        if free_margin is not None and free_margin < margin_min:
            logger.warning(f"RiskEngine: free margin ${free_margin:.2f} below ${margin_min:.2f} ({self.margin_min_pct}% of ${self._current_equity:.2f}) — pausing trades")
            return False

        # ── Total portfolio SL risk check ──
        # Sum SL risk across all open positions; reject if total exceeds max_portfolio_sl_pct of equity
        portfolio_sl = self._get_total_portfolio_sl_risk()
        # For small accounts (<$100), raise portfolio SL cap to 80% to allow more positions
        effective_portfolio_sl_pct = self.max_portfolio_sl_pct
        if self._current_equity < 100:
            effective_portfolio_sl_pct = max(effective_portfolio_sl_pct, 80.0)
        max_portfolio_sl_dollars = abs(effective_portfolio_sl_pct / 100.0 * self._current_equity)
        if portfolio_sl > max_portfolio_sl_dollars and max_portfolio_sl_dollars > 0:
            logger.warning(
                f"RiskEngine: trade blocked — total SL risk ${portfolio_sl:.2f} > "
                f"{effective_portfolio_sl_pct}% of equity (${max_portfolio_sl_dollars:.2f})"
            )
            return False

        # ── Directional exposure check ──
        # Reject if > max_directional_pct% of positions are in the same direction
        if symbol and self.max_directional_pct > 0:
            directional_check = self._check_directional_exposure(symbol)
            if not directional_check:
                return False

        return True

    def can_trade_symbol(self, symbol: str) -> tuple:
        """Check if a specific symbol can trade. Returns (allowed, reason)."""
        if not self.can_trade(symbol):
            if self.halt:
                return False, f"halted ({self._halt_reason})"
            if self.daily_trades >= self.max_daily_trades:
                return False, "daily_trade_limit"
            open_positions = self._get_open_positions_count()
            if open_positions >= self.max_open_positions:
                return False, f"max_positions_total ({open_positions}/{self.max_open_positions})"
            symbol_positions = self._get_symbol_positions_count(symbol)
            if symbol_positions >= self.max_positions_per_symbol:
                return False, f"max_positions_{symbol} ({symbol_positions}/{self.max_positions_per_symbol})"
            return False, "unknown"
        return True, "ok"

    def _get_open_positions_count(self) -> int:
        """Get total number of open positions from MT5."""
        # Use cached count from server updates if available
        cached = getattr(self, "_mt5_position_count", None)
        if cached is not None:
            return cached
        # Fallback: try MT5 directly
        try:
            import MetaTrader5 as mt5
            if mt5.initialize():
                positions = mt5.positions_get()
                return len(positions) if positions else 0
        except Exception:
            pass
        return 0

    def _get_symbol_positions_count(self, symbol: str) -> int:
        """Get number of open positions for a specific symbol."""
        try:
            import MetaTrader5 as mt5
            if mt5.initialize():
                positions = mt5.positions_get(symbol)
                return len(positions) if positions else 0
        except Exception:
            pass
        # Fallback: check cached data
        cached_positions = getattr(self, "_mt5_positions_list", [])
        return sum(1 for p in cached_positions if getattr(p, 'symbol', '') == symbol)

    def _get_total_portfolio_sl_risk(self) -> float:
        """Calculate total SL risk across all open positions.

        For each position: risk = |current_price - SL| * volume * tick_value / tick_size
        Sum across all positions and return total dollar risk.
        """
        total_risk = 0.0
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                return 0.0
            positions = mt5.positions_get()
            if not positions:
                return 0.0
            for p in positions:
                if p.sl > 0 and p.volume > 0:
                    sl_distance = abs(p.price_open - p.sl)
                    # Get tick value for this symbol
                    sym_info = mt5.symbol_info(p.symbol)
                    if sym_info:
                        tick_value = getattr(sym_info, 'trade_tick_value', 1.0) or 1.0
                        tick_size = getattr(sym_info, 'trade_tick_size', 1.0) or 1.0
                        if tick_size > 0:
                            risk = sl_distance / tick_size * tick_value * p.volume
                        else:
                            risk = sl_distance * p.volume * 10  # rough estimate
                    else:
                        risk = sl_distance * p.volume * 10
                    total_risk += risk
        except Exception as e:
            logger.debug(f"Portfolio SL risk calculation failed: {e}")
        return total_risk

    def _check_directional_exposure(self, symbol: str) -> bool:
        """Check if adding a position would make directional exposure too concentrated.

        Returns True if the trade is allowed, False if blocked.
        """
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                return True  # Allow if we can't check
            positions = mt5.positions_get()
            if not positions or len(positions) < 3:
                return True  # Not enough positions to worry about

            long_count = sum(1 for p in positions if p.type == 0)  # BUY
            short_count = sum(1 for p in positions if p.type == 1)  # SELL
            total = long_count + short_count

            if total < 3:
                return True

            # Check if new trade would push directional concentration past limit
            long_pct = long_count / total * 100
            short_pct = short_count / total * 100

            # If 70%+ of positions are already in one direction, block same-direction trades
            if long_pct >= self.max_directional_pct or short_pct >= self.max_directional_pct:
                dominant = "BUY" if long_pct >= short_pct else "SELL"
                dominated_pct = max(long_pct, short_pct)
                logger.warning(
                    f"RiskEngine: directional exposure blocked — {dominated_pct:.0f}% {dominant} "
                    f"({long_count} long, {short_count} short). Max allowed: {self.max_directional_pct}%"
                )
                return False
        except Exception as e:
            logger.debug(f"Directional exposure check failed: {e}")
        return True

    def get_halt_reason(self) -> str:
        """Return the reason for the current halt, or empty string."""
        return self._halt_reason

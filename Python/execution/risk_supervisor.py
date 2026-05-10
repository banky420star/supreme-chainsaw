"""Execution-layer RiskSupervisor — mirrors RiskEngine API.

Tracks daily PnL, drawdown, trade count, losing trades per symbol, error
count, and halt flags. Designed to be a drop-in companion to
`Python.risk_engine.RiskEngine` inside the execution package.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import yaml
from loguru import logger


_CFG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config.yaml",
)


class RiskSupervisor:
    """Risk supervisor matching the RiskEngine public API.

    Methods:
      can_trade(symbol=None)
      record_trade(symbol)
      record_pnl(amount)
      record_trade_result(symbol, pnl)
      record_error()
      update_equity(equity)
      reset_daily()
    """

    def __init__(self, config: dict | None = None):
        cfg = config or self._load_cfg()
        risk_cfg = cfg.get("risk", {}) if isinstance(cfg, dict) else {}
        trading_cfg = cfg.get("trading", {}) if isinstance(cfg, dict) else {}

        self.max_daily_loss = float(risk_cfg.get("max_daily_loss", 1000))
        self.max_daily_trades = int(risk_cfg.get("max_daily_trades", 50))
        self.max_daily_trades_per_symbol = int(risk_cfg.get("max_daily_trades_per_symbol", 50))
        self.max_daily_losing_trades_per_symbol = int(risk_cfg.get("max_daily_losing_trades_per_symbol", 10))
        self.max_lots = float(risk_cfg.get("max_lots", 1.0))
        self.max_open_positions = int(risk_cfg.get("max_open_positions", 8))
        self.max_positions_per_symbol = int(risk_cfg.get("max_positions_per_symbol", 2))
        self.max_drawdown_pct = float(risk_cfg.get("max_drawdown_pct", 8.0))

        self.default_symbol_profile = {
            "entry_deviation": int(trading_cfg.get("entry_deviation", 20)),
            "sl_points": int(trading_cfg.get("sl_points", 250)),
            "tp_points": int(trading_cfg.get("tp_points", 450)),
        }
        self.symbol_profiles = trading_cfg.get("symbol_profiles", {}) or {}

        # Mutable daily state
        self.realized_pnl_today = 0.0
        self.daily_trades = 0
        self.daily_trades_by_symbol: dict[str, int] = {}
        self.daily_losing_trades_by_symbol: dict[str, int] = {}
        self.halt = False
        self.error_halt = False
        self.error_count = 0
        self.current_dd = 0.0
        self.peak_equity: float | None = None
        self._current_equity = 0.0
        self._halt_reason = ""
        self.last_reset_day = datetime.now(timezone.utc).date()

    @staticmethod
    def _load_cfg() -> dict:
        try:
            with open(_CFG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def reset_daily(self) -> None:
        self.realized_pnl_today = 0.0
        self.daily_trades = 0
        self.daily_trades_by_symbol = {}
        self.daily_losing_trades_by_symbol = {}
        self.error_count = 0
        if not self.error_halt:
            self.halt = False
            self._halt_reason = ""
        self.last_reset_day = datetime.now(timezone.utc).date()

    def maybe_roll_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self.last_reset_day:
            self.reset_daily()

    def record_trade(self, symbol: str | None = None) -> None:
        self.maybe_roll_day()
        self.daily_trades += 1
        if symbol:
            key = str(symbol)
            self.daily_trades_by_symbol[key] = int(self.daily_trades_by_symbol.get(key, 0)) + 1

    def record_pnl(self, pnl: float) -> None:
        self.maybe_roll_day()
        self.realized_pnl_today += float(pnl)
        if self.realized_pnl_today <= -abs(self.max_daily_loss):
            self.halt = True
            self._halt_reason = "daily_loss"

    def record_trade_result(self, symbol: str | None, pnl: float) -> None:
        self.maybe_roll_day()
        self.record_pnl(pnl)
        if symbol is None:
            return
        if float(pnl) < 0.0:
            key = str(symbol)
            self.daily_losing_trades_by_symbol[key] = int(self.daily_losing_trades_by_symbol.get(key, 0)) + 1

    def update_equity(self, equity: float) -> None:
        eq = float(equity)
        self._current_equity = eq
        if self.peak_equity is None:
            self.peak_equity = eq
            self.current_dd = 0.0
            return
        self.peak_equity = max(self.peak_equity, eq)
        if self.peak_equity > 0:
            self.current_dd = (self.peak_equity - eq) / self.peak_equity * 100.0

    def record_error(self) -> None:
        self.error_count += 1
        if self.error_count >= 3:
            self.halt = True
            self.error_halt = True
            self._halt_reason = "consecutive_errors"

    def can_trade(self, symbol: str | None = None) -> bool:
        self.maybe_roll_day()
        if self.halt:
            logger.debug(f"RiskSupervisor: trade blocked — halt ({self._halt_reason})")
            return False
        if self.daily_trades >= self.max_daily_trades:
            logger.debug(
                f"RiskSupervisor: trade blocked — daily trade limit "
                f"({self.daily_trades}/{self.max_daily_trades})"
            )
            return False
        if symbol:
            key = str(symbol)
            if int(self.daily_trades_by_symbol.get(key, 0)) >= self.max_daily_trades_per_symbol:
                return False
            if int(self.daily_losing_trades_by_symbol.get(key, 0)) >= self.max_daily_losing_trades_per_symbol:
                return False
        return True

    def get_symbol_profile(self, symbol: str) -> dict:
        prof = self.default_symbol_profile.copy()
        sym_prof = self.symbol_profiles.get(symbol, {})
        if isinstance(sym_prof, dict):
            prof.update(sym_prof)
        return prof

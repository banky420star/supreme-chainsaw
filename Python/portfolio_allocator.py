"""
PortfolioAllocator — Dynamic risk budget allocation across symbols.

Allocates risk budget proportional to recent per-symbol performance.
Better-performing symbols get more budget; poor performers get reduced.
Total portfolio heat is capped at max_portfolio_heat.

Scales from 1 symbol to N symbols, from $50 to $250K+.
"""
from __future__ import annotations

import os
from collections import defaultdict, deque

import numpy as np
from loguru import logger


class PortfolioAllocator:
    """Dynamic risk budget allocation across symbols based on performance."""

    def __init__(self, config: dict, symbols: list[str]):
        self.symbols = symbols
        self.max_portfolio_heat = float(config.get("max_portfolio_heat", 0.06))  # 6% max total risk
        self.min_symbol_heat = float(config.get("min_symbol_heat", 0.005))  # 0.5% minimum per symbol
        self.max_symbol_heat = float(config.get("max_symbol_heat", 0.03))  # 3% max per symbol
        self.correlation_penalty = float(config.get("correlation_penalty", 0.5))
        self.history_window = int(config.get("history_window", 50))

        # Per-symbol trade history: deque of (pnl, timestamp) tuples
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.history_window))

        # Correlation matrix (updated periodically from returns)
        self._correlation_matrix = np.eye(len(symbols))

        logger.info(
            f"PortfolioAllocator initialized: {len(symbols)} symbols, "
            f"max_heat={self.max_portfolio_heat:.1%}, "
            f"min_heat={self.min_symbol_heat:.1%}, "
            f"max_per_symbol={self.max_symbol_heat:.1%}"
        )

    def allocate(self, equity: float, per_symbol_performance: dict | None = None) -> dict[str, float]:
        """Return risk budget allocation per symbol.

        Args:
            equity: Current account equity
            per_symbol_performance: Optional dict of symbol -> {"win_rate", "avg_pnl", "sharpe"}

        Returns:
            dict of symbol -> heat_pct (e.g. {"EURUSDm": 0.02, ...})
            Sum of all heat_pct <= max_portfolio_heat
        """
        if equity <= 0:
            return {s: self.min_symbol_heat for s in self.symbols}

        scores = self._compute_performance_scores()

        # Apply correlation penalty for co-moving assets
        if len(self.symbols) > 1:
            scores = self._apply_correlation_penalty(scores)

        # Normalize so total = max_portfolio_heat
        total_score = sum(scores.values())
        if total_score <= 0:
            # Equal allocation if no performance data
            equal = self.max_portfolio_heat / max(len(self.symbols), 1)
            return {s: min(equal, self.max_symbol_heat) for s in self.symbols}

        allocations = {}
        for sym in self.symbols:
            budget_pct = (scores[sym] / total_score) * self.max_portfolio_heat
            # Clamp to per-symbol limits
            budget_pct = max(self.min_symbol_heat, min(budget_pct, self.max_symbol_heat))
            allocations[sym] = budget_pct

        # Re-normalize if clamping pushed total over max_portfolio_heat
        total_alloc = sum(allocations.values())
        if total_alloc > self.max_portfolio_heat:
            scale = self.max_portfolio_heat / total_alloc
            allocations = {s: v * scale for s, v in allocations.items()}

        return allocations

    def get_lot_multiplier(self, symbol: str, equity: float) -> float:
        """Get lot size multiplier for a symbol based on its allocation.

        Returns a multiplier (0.1 to 2.0) to apply to the base lot size.
        """
        allocs = self.allocate(equity)
        heat = allocs.get(symbol, self.min_symbol_heat)
        # Convert heat to multiplier: 1% heat = 1.0x, 2% = 2.0x, 0.5% = 0.5x
        multiplier = heat / 0.01
        return max(0.1, min(2.0, multiplier))

    def record_trade_result(self, symbol: str, pnl: float):
        """Record a trade result for performance tracking."""
        import time
        self._history[symbol].append((pnl, time.time()))

    def _compute_performance_scores(self) -> dict[str, float]:
        """Compute performance score per symbol from trade history.

        Uses a Sharpe-like metric: win_rate * avg_win - (1 - win_rate) * avg_loss
        Normalized to [0.1, 1.0] range.
        """
        scores = {}
        for sym in self.symbols:
            history = self._history.get(sym, [])
            if len(history) < 5:
                scores[sym] = 0.5  # neutral for new symbols
                continue

            pnls = [p for p, _ in history]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]

            win_rate = len(wins) / len(pnls) if pnls else 0.5
            avg_win = np.mean(wins) if wins else 0
            avg_loss = abs(np.mean(losses)) if losses else 1

            # Expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

            # Normalize to [0.1, 1.0] — 0.5 = break-even
            scores[sym] = max(0.1, min(1.0, 0.5 + expectancy * 10))

        return scores

    def _apply_correlation_penalty(self, scores: dict[str, float]) -> dict[str, float]:
        """Reduce allocation for highly correlated symbols.

        If two symbols are highly correlated (e.g., EURUSD and GBPUSD),
        reduce both their allocations to avoid concentrated risk.
        """
        # Simple heuristic: FX pairs with USD as quote are correlated
        fx_groups = {
            "usd_quote": {"EURUSDm", "GBPUSDm", "AUDUSDm", "NZDUSDm"},
            "usd_base": {"USDJPYm", "USDCADm", "USDCHFm"},
            "commodity": {"XAUUSDm"},
            "crypto": {"BTCUSDm"},
        }

        adjusted = dict(scores)
        for group_name, group_syms in fx_groups.items():
            active = [s for s in group_syms if s in self.symbols]
            if len(active) <= 1:
                continue
            # If multiple symbols from the same group, reduce each by penalty
            total_group_score = sum(adjusted.get(s, 0.5) for s in active)
            for s in active:
                if total_group_score > 0:
                    # Reduce by correlation_penalty for each additional correlated asset
                    penalty = self.correlation_penalty * (len(active) - 1) / len(active)
                    adjusted[s] *= (1.0 - penalty)

        return adjusted

    def update_correlation_matrix(self, returns_data: dict[str, list[float]]):
        """Update the correlation matrix from per-symbol returns.

        Called periodically (e.g., weekly) to reflect changing correlations.
        """
        if len(returns_data) < 2:
            return

        try:
            # Build aligned returns matrix
            min_len = min(len(v) for v in returns_data.values() if v)
            if min_len < 10:
                return

            aligned = np.array([v[-min_len:] for v in returns_data.values() if len(v) >= min_len])
            if aligned.shape[0] < 2:
                return

            self._correlation_matrix = np.corrcoef(aligned)
            logger.debug(f"PortfolioAllocator: correlation matrix updated ({aligned.shape[0]} symbols)")
        except Exception as e:
            logger.debug(f"Correlation matrix update failed: {e}")
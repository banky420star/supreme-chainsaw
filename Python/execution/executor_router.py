"""ExecutorRouter — routes trade intents to the correct executor.

  paper_sim   → PaperExecutor
  demo_live   → MT5DemoExecutor
  real_live*  → MT5DemoExecutor (locked) or raw MT5Executor (unlocked)

No raw orders are emitted from the PPO policy; all intents pass through
GateEngine before reaching an executor.
"""

from __future__ import annotations

from typing import Any

from Python.execution.mode_resolver import resolve_mode
from Python.execution.paper_executor import PaperExecutor
from Python.execution.mt5_demo_executor import MT5DemoExecutor


class ExecutorRouter:
    """Routes trade intents based on the current execution mode."""

    def __init__(
        self,
        config: dict | None = None,
        risk_supervisor=None,
        mt5_executor=None,
    ):
        self.config = config or {}
        self.mode = resolve_mode(self.config)
        self.risk = risk_supervisor

        if self.mode == "paper_sim":
            self._executor = PaperExecutor(
                config=self.config,
                risk_supervisor=risk_supervisor,
            )
        elif self.mode in ("demo_live", "real_live_locked", "real_live"):
            # Demo and locked-real both route through the guarded demo executor.
            # Only an explicit, fully-gated real_live path could reach the raw
            # MT5Executor, and that is blocked here by design.
            self._executor = MT5DemoExecutor(
                config=self.config,
                risk_supervisor=risk_supervisor,
                mt5_executor=mt5_executor,
            )
        else:
            # Safe fallback
            self._executor = PaperExecutor(
                config=self.config,
                risk_supervisor=risk_supervisor,
            )

    def submit(self, intent: dict[str, Any]) -> dict[str, Any]:
        """Send a gated trade intent to the active executor.

        Returns an execution metadata dict with at least:
          { "executed": bool, "mode": str, "reason": str }
        """
        return self._executor.execute(intent)

    def get_positions(self, symbol: str | None = None) -> list[Any]:
        """Return open positions from the active executor."""
        return self._executor.get_positions(symbol)

    @property
    def active_executor_name(self) -> str:
        return type(self._executor).__name__

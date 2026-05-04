---
name: Risk Engine Hardening Test Notes
description: Key findings from testing Phase 1 hardening features in risk_engine.py
type: project
---

RiskEngine Phase 1 hardening introduces: max_hourly_loss (with _hourly_pnl deque), max_drawdown_pct auto-halt, max_open_positions (total and per-symbol), can_trade_symbol(symbol) returning (allowed, reason) tuple, get_halt_reason(), _check_hourly_reset() at hour boundaries, _halt_reason field.

**Why:** Phase 1 hardening refactored the halt tracking from error_halt boolean to _halt_reason string.

**How to apply:** When testing RiskEngine:
- Monkeypatch `_bootstrap_equity` as `staticmethod(lambda: value)` because it is a @staticmethod, otherwise `self._bootstrap_equity()` passes `self` as arg
- On this Windows machine, MT5 IS importable, so `_get_symbol_positions_count` bypasses the `_mt5_positions_list` fallback. Must mock the method directly with monkeypatch for per-symbol position tests.
- In `record_pnl`, daily loss check runs FIRST, then hourly loss check runs SECOND and overwrites `_halt_reason`. When both trigger, "hourly_loss" is the final reason.
- `reset_daily` preserves halt only when `_halt_reason` contains "daily_loss". All other halt reasons get cleared.
- The old test file `test_risk_engine_fixes.py` is broken: references removed names `_CFG_PATH`, `error_halt`, `maybe_roll_day`.
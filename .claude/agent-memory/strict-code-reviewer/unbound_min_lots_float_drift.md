---
name: Unbound variable and float drift in mt5_executor.py
description: min_lots used before assignment on ATR fallback path; round(x/step)*step produces float artifacts
type: project
---

**Unbound `min_lots`**: In `compute_risk_adjusted_lots`, when `atr > 0` but `tick_size <= 0`, line 339 uses `min_lots` before it is assigned on line 346. The only prior assignment (line 316) is inside an `if atr <= 0` block that returns early. This causes NameError at runtime.

**Float drift**: `round(lots / 0.02) * 0.02` at lines 350-351 and 552-553 produces float artifacts (e.g. 0.06000000000000001). MT5 rejects orders with imprecise volume. Should read `volume_step` from `symbol_info` and round to that step's precision.
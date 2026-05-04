---
name: Config priority conflicts in chain_gambler
description: min_lots and lot_step have conflicting sources (YAML vs env var vs hardcoded) that create dead config and runtime bugs
type: project
---

Per-symbol YAML configs define `min_lots` and other risk params, but `mt5_executor.py` and `order_manager.py` read `AGI_MIN_LOTS` from env var instead of YAML. The YAML `min_lots` field is dead code. `start_live.py` sets `AGI_MIN_LOTS=0.01` which overrides the YAML value of 0.02, creating a three-way inconsistency. `lot_step=0.02` is hardcoded in `mt5_executor.py` lines 350 and 552 instead of reading from MT5 `symbol_info.volume_step`. The `_load_symbol_risk_config` function in `order_manager.py` is the correct pattern for reading YAML config with TTL cache, but `mt5_executor.py` does its own inline YAML reads without caching.
# Decision PPO — Rich Autonomous Trade Decision Brain

**Status:** Implemented (v1 core, 2026-05-28; Execution Path Finalization 2026-05-28)  
**Role:** High-level "what trade to do" policy. Outputs complete, executable trade specifications.  
Primary execution: pure Python OrderManager+MT5Executor (mql5_bridge=False) for Windows direct + rich telemetry back to PPO. Optional MQL5 via env. Full rich features (risk sizing, ladders, trailing) supported end-to-end.  
**Lower layer:** Executors (Python `order_manager`/`action_translator`, MQL5 `ChainGambler_Executor`) handle placement, monitoring, fills, and lifecycle.

## Architecture Overview

```
Multi-Timeframe Features (1m + 5m + 15m + 1h)
        + best_features_per_symbol.yaml (per-symbol ATR/RSI/etc params)
                │
                ▼
Feature Extractor (LSTM / Dreamer / Transformer backbone or env built-in)
                │
                ▼
DecisionHead (drl/decision_head.py)  OR  SB3 PPO on large Box(18,)
                │
                ▼
Raw action vector [-1,1]^DECISION_ACTION_DIM
                │
                ▼
TradingEnv.decode_action(...)  →  DecisionSpec + rich meta dict
                │
        ┌───────┴───────────────────────────────┐
        │                                       │
   TrainingEnv simulation                 Live / Executor
   (full P&L + risk + partials +          (action_translator + MQL5)
    time exits + ATR TP/SL + trailing)          │
        │                                       │
        ▼                                       ▼
TradingReward (hold_steps, risk_used)     decision_command JSON
        │                                       │
   End-to-end gradients                     ChainGambler / Python exec
```

The **Decision PPO** is deliberately separated from execution mechanics. This enables:
- End-to-end training on realized economics (including sophisticated exits).
- Easy distillation/export to MQL5 native inference.
- Swappable executors without retraining the brain.

## DecisionSpec (Canonical Structured Output)

`DecisionSpec` (defined in `drl/trading_env.py`) + `.to_dict()` / `.to_json()` is the primary artifact.

Full fields (see source for defaults):

- `direction`: float (-1 sell ... +1 buy)
- `confidence`
- `lot_spec`:
  - `mode`: "risk_based" | "fixed" | "vol_target"
  - `risk_pct_equity`, `fixed_lots`, `vol_target_pct`, `atr_mult_for_size`
- `entry`: {type: "market"|"limit"|"stop", offset_pct, price?}
- `tp` / `sl`: {type: "pct" | "atr" | "price" | "rr", value, rr, atr_period}
- `trailing`:
  - enabled, type ("pct"|"atr"), distance, step, activation_trigger_*, atr_mult
- `partial_close`:
  - enabled, levels: [{trigger_profit_pct, close_pct, move_sl_to_be}, ...]
- `full_close`: {max_hold_bars, max_hold_minutes, force_eod, volatility_exit...}
- `breakeven`: {enabled, trigger_fav_pct, lock_profit_pct, type}
- `risk`, raw_action, legacy flags, action_version

**JSON example** (what executors receive):

```json
{
  "version": "decision_ppo_v1",
  "symbol": "XAUUSDm",
  "direction": 1,
  "lot_spec": {"mode": "risk_based", "risk_pct_equity": 0.007},
  "entry": {"type": "market"},
  "take_profit": {"type": "atr", "value": 1.8, "atr_period": 10},
  "stop_loss": {"type": "pct", "value": 0.004},
  "trailing_stop": {"enabled": true, "type": "pct", "distance": 0.0025, "step": 0.001},
  "partial_close": {"enabled": true, "levels": [{"trigger_profit_pct": 0.006, "close_pct": 0.5, "move_sl_to_be": true}]},
  "full_close_conditions": {"max_hold_bars": 180},
  "breakeven": {"enabled": true, "trigger_fav_pct": 0.0025},
  "confidence": 0.78,
  "source": "decision_ppo"
}
```

## Usage

### 1. Training (Decision PPO mode)

```python
from drl.trading_env import TradingEnv
from training.train_drl import make_env  # or direct

env = TradingEnv(
    df,
    action_config={
        "decision_ppo": True,
        "decision_action_dim": 18,
    },
    symbol="XAUUSDm",
    feature_version="multitimeframe_best",  # new standard MTF
)
# action_space is now Box(18,)
# PPO (SB3) or custom DecisionHead policy trains directly
```

Use `drl/decision_head.py:DecisionHead` + `DecisionPPOActorCritic` for fully custom loops or distillation.

### 2. Inference / Live (HybridBrain / Autonomy)

`predict_ppo_action` path continues to work (returns rich meta when model trained on Decision space).

```python
action_meta = brain.predict_ppo_action(symbol, df)
# action_meta now contains:
#   - legacy keys (compat)
#   - "decision_spec": DecisionSpec instance
#   - "decision_spec_dict"
#   - "lot_spec", "tp_spec", ...
```

### 3. Executor Handoff

```python
from Python.action_translator import (
    translate_trade_action,
    decision_spec_to_executor_command,
    serialize_decision_for_mql5,
)

cmd = decision_spec_to_executor_command(action_meta["decision_spec"], symbol)
json_for_mql5 = serialize_decision_for_mql5(cmd)
# Send to ChainGambler EA (file drop, named pipe, or socket)
```

`translate_trade_action` automatically upgrades rich actions while preserving old flat fields.

### 4. Inside TradingEnv (simulation for reward)

Rich DecisionSpec drives:
- ATR-aware TP/SL computation at entry
- Configurable trailing + breakeven
- Multi-level partial closes (with BE moves)
- `max_hold_bars` time exits
- Proper `hold_steps` + `risk_used` passed to `TradingReward`

## Files Changed / Added

- `drl/trading_env.py`: DecisionSpec, extended decode_action (full rich + legacy), simulation logic, ATR, MTF hook, reward integration.
- `drl/decision_head.py`: New — `DecisionHead`, `DecisionPPOActorCritic`.
- `drl/ppo_agent.py`: Decision PPO helpers + import.
- `Python/action_translator.py`: Rich command builder + `decision_spec_to_executor_command`.
- `tests/test_trading_env.py`: Rich decode + XAU test data smoke tests.
- `docs/DECISION_PPO.md`: This file.
- `runtime/agent_status/decision_ppo_implementation.json`: Status marker.

## Compatibility Guarantees

- All legacy 1/3/6-dim actions decode exactly as before.
- Existing models / handoff watcher / supervisor / TUI paths unaffected.
- `action_version` and `decision_ppo` flags present for downstream branching.
- MTF data: `set_mtf_data()` + `feature_version="multitimeframe_best"` supported (training pipeline primary consumer).

## Future Work (Post v1)

- Full custom SB3 `ActorCriticPolicy` using DecisionHead (discrete heads for entry_type / tp_type).
- MQL5 native DecisionHead port (CNet equivalent of the 18-dim head).
- Protobuf spec + gRPC handoff option.
- Dynamic ATR-period per decision.
- Portfolio-level constraints in DecisionSpec.
- Champion Decision PPO promotion gates (separate from current exposure-only models).

## References

- `configs/best_features_per_symbol.yaml`
- `Python/features/multitimeframe_builder.py`
- `Python/rewards/reward_function.py` (TradingReward)
- `mql5/Experts/ChainGambler/`
- `docs/MQL5_EXECUTION_LAYER_DESIGN.md`
- `drl/trading_env.py` (DecisionSpec + decode_action source of truth)

**Decision PPO turns the agent from "how much exposure?" into a true autonomous trader that specifies complete, risk-aware trade plans.**

End-to-end training on rich exits + risk metrics is now possible while keeping the execution layer clean and swappable.

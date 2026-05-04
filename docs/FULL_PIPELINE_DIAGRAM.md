# Chain Gambler - Full Training Pipeline Loop

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CHAIN GAMBLER TRAINING PIPELINE                        │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: DATA INGESTION                                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                       │
│  │  MetaTrader5 │    │   Yahoo      │    │  Data Cache  │                       │
│  │   Live Feed  │────▶│  Finance     │────▶│   (Parquet)  │                       │
│  └──────────────┘    └──────────────┘    └──────────────┘                       │
│         │                                              │                         │
│         ▼                                              ▼                         │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │              Python/data_feed.py                             │               │
│  │  • fetch_training_data()                                     │               │
│  │  • get_combined_training_df()                                │               │
│  │  • 100,000 candle default                                    │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                   │                                              │
└───────────────────────────────────┼────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: FEATURE ENGINEERING                                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │           Python/feature_pipeline.py                       │               │
│  └────────────────────────────────────────────────────────────┘               │
│                         │                                                        │
│         ┌───────────────┼───────────────┬───────────────┐                       │
│         ▼               ▼               ▼               ▼                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
│  │ ENGINEERED   │ │ ULTIMATE_150   │ │ Raw Features │ │ LSTM Frame   │          │
│  │     V2       │ │  (Default)     │ │              │ │ Builder      │          │
│  │              │ │                │ │              │ │              │          │
│  │ • RSI/ATR    │ │ • 150 features │ │ Open/High   │ │ Sequences    │          │
│  │ • EMA        │ │ • Auto-ML      │ │ Low/Close   │ │ 60-timesteps │          │
│  │ • Patterns   │ │ • SHAP support │ │ Volume      │ │              │          │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: LSTM CONTEXT TRAINING                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │              training/train_lstm.py                        │               │
│  └────────────────────────────────────────────────────────────┘               │
│                         │                                                        │
│    ┌────────────────────┼────────────────────┐                                 │
│    ▼                    ▼                    ▼                                 │
│ ┌──────────┐      ┌──────────┐        ┌──────────────┐                         │
│ │EURUSDm   │      │BTCUSDm   │        │  XAUUSDm     │                         │
│ │TRAINING  │      │TRAINING  │        │  TRAINING    │                         │
│ │          │      │          │        │              │                         │
│ │• 60-seq  │      │• 60-seq  │        │• 60-seq      │                         │
│ │• Adam    │      │• Adam    │        │• Adam        │                         │
│ │• 50 ep   │      │• 50 ep   │        │• 50 ep       │                         │
│ │• CE Loss │      │• CE Loss │        │• CE Loss     │                         │
│ └────┬─────┘      └────┬─────┘        └──────┬───────┘                         │
│      │                  │                     │                                 │
│      ▼                  ▼                     ▼                                 │
│ ┌────────────────────────────────────────────────────────────┐               │
│ │                 OUTPUT: models/per_symbol/                   │               │
│ │              lstm_EURUSDm.pt, lstm_BTCUSDm.pt...           │               │
│ └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Classification Targets:                                                        │
│  • 0 = NEUTRAL (hold)                                                          │
│  • 1 = BUY (future return > threshold + RSI > 52)                              │
│  • 2 = SELL (future return < -threshold + RSI < 48)                            │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 4: PPO POLICY TRAINING                                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │              training/train_drl.py                         │               │
│  └────────────────────────────────────────────────────────────┘               │
│                         │                                                        │
│         ┌───────────────┼───────────────┬───────────────┐                       │
│         ▼               ▼               ▼               ▼                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
│  │   TradingEnv │ │ LSTMFeature  │ │  PPO Agent   │ │ VecNormalize │          │
│  │              │ │  Extractor   │ │              │ │              │          │
│  │ • Custom SB3│ │              │ │ • MlpPolicy  │ │ • Observation│          │
│  │ • 2103 obs  │ │ • LSTM layer │ │ • ClipRange  │ │   Normalizer │          │
│  │ • 3 actions │ │ • 150 feat   │ │ • EntCoef    │ │ • RewardScale│          │
│  │ • Rewards   │ │ • Portfolio  │ │ • Gamma=0.99 │ │              │          │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘          │
│                                                                                  │
│  Training Flow:                                                                 │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │  1. Fetch Training Data → 100k candles                      │               │
│  │  2. Build Features → ultimate_150                          │               │
│  │  3. Load LSTM → lstm_{symbol}.pt                           │               │
│  │  4. Create VecEnv → DummyVecEnv / SubprocVecEnv            │               │
│  │  5. Train PPO → 100k timesteps                             │               │
│  │  6. EvalCallback → Saves best model                        │               │
│  │  7. Save Candidate → models/registry/candidates/           │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Environment Variables:                                                         │
│  • AGI_DRL_SYMBOL=BTCUSDm                                                       │
│  • AGI_FEATURE_VERSION=ultimate_150                                             │
│  • AGI_USE_SUBPROC_VECENV=1 (parallel training)                                 │
│  • AGI_TOTAL_TIMESTEPS=100000                                                  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 5: CANDIDATE EVALUATION                                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │            Python/model_evaluator.py                       │               │
│  │         evaluate_candidate_vs_champion()                   │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Evaluation Gates (All Must Pass):                                              │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │  1. MAX DRAWDOWN   ≤ 10% (default)                         │               │
│  │  2. MIN SHARPE     ≥ 0.30                                  │               │
│  │  3. MIN RETURN     ≥ 1.5%                                 │
│  │  4. SCORE MARGIN   ≥ 0.30 (vs champion)                    │               │
│  │  5. MIN STEPS      ≥ 600 per symbol                        │               │
│  │  6. PASS RATE      ≥ 80%                                   │               │
│  │  7. FORWARD WINDOWS ≥ 2/3 pass rate                        │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Evaluation Metrics:                                                            │
│  • Average Score (PnL per step)                                                │
│  • Win Rate (% profitable episodes)                                            │
│  • Sharpe Ratio (risk-adjusted return)                                         │
│  • Max Drawdown (peak-to-trough decline)                                      │
│  • Per-symbol Performance                                                      │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 6: CHAMPION/CANARY REGISTRY                                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │            Python/model_registry.py                          │               │
│  │                    ModelRegistry                             │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Per-Symbol Model Structure:                                                    │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │ models/registry/active.json                                │               │
│  │ {                                                          │               │
│  │   "symbols": {                                            │               │
│  │     "EURUSDm": {                                          │               │
│  │       "champion": "ppo_20260424_141609",                  │               │
│  │       "canary": null,                                      │               │
│  │       "canary_policy": {...},                              │               │
│  │       "canary_state": {...}                                │               │
│  │     },                                                     │               │
│  │     "BTCUSDm": {...},                                     │               │
│  │     "XAUUSDm": {...}                                      │               │
│  │   }                                                        │               │
│  │ }                                                          │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Champion History Tracking:                                                     │
│  • Who replaced whom                                                           │
│  • When promotion occurred                                                      │
│  • Performance delta                                                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 7: CANARY PROMOTION POLICY                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │            tools/champion_cycle.py                          │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Evaluation Flow:                                                               │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│  │ TRAIN    │────▶│ EVALUATE │────▶│  GATE    │────▶│ PROMOTE  │               │
│  │ Candidate│     │ vs Champ │     │ Check    │     │ or ROLL  │               │
│  └──────────┘     └──────────┘     └──────────┘     └──────────┘               │
│                                                          │                      │
│                                                          ▼                      │
│  Promotion Criteria:                              ┌──────────────┐             │
│  ┌─────────────────────────────────────────────┐   │              │             │
│  │  All Gates Pass + Score > Champion + 0.25   │──▶│   PROMOTE    │             │
│  │                                             │   │  to Champion │             │
│  └─────────────────────────────────────────────┘   │              │             │
│                                                    └──────────────┘             │
│  Rollback Criteria:                                                              │
│  ┌─────────────────────────────────────────────┐   ┌──────────────┐             │
│  │  Drawdown > 12% OR PnL < -$75 OR            │──▶│   ROLLBACK   │             │
│  │  Trades < 10 OR Runtime < 45 min            │   │  to Champion │             │
│  └─────────────────────────────────────────────┘   └──────────────┘             │
│                                                                                  │
│  Canary Policy Config:                                                          │
│  • max_drawdown: 10% (default)                                                  │
│  • min_sharpe: 0.30                                                             │
│  • min_return: 1.5%                                                             │
│  • min_runtime_minutes: 45                                                      │
│  • min_trades: 10                                                               │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 8: LIVE INFERENCE (Runtime)                                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │            Python/hybrid_brain.py                           │               │
│  │                    decide() Flow                             │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Decision Pipeline Steps:                                                        │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │  1. Fetch latest candles from MT5                         │               │
│  │  2. Build ultimate_150 features                            │               │
│  │  3. Run LSTM → Get volatility regime                       │               │
│  │  4. Load PPO Champion → Get policy action                  │               │
│  │  5. Load Dreamer (if enabled) → Get target                 │               │
│  │  6. Blend targets (PPO + Dreamer weights)                  │               │
│  │  7. Apply confidence threshold                             │               │
│  │  8. Apply risk engine filters                              │               │
│  │  9. Reversal Detection Check (if enabled)                │               │
│  │  10. Speed Simulation (if paper trading)                 │               │
│  │  11. Execute via MT5Executor                               │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Model Blending:                                                                │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │  final_target = ppo_target × ppo_blend_weight             │               │
│  │              + dreamer_target × dreamer_blend_weight      │               │
│  │                                                            │               │
│  │  Default: ppo_blend = 0.70, dreamer_blend = 0.30          │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 9: AUTONOMY LOOP (Continuous Improvement)                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │            Python/autonomy_loop.py                          │               │
│  │              AutonomyLoop Class                            │               │
│  └─────────────────────────────────────────────────────────────────────────────┘
│                                                                                  │
│  Cycle Flow (Every ~1 hour by default):                                       │
│  ┌────────────────────────────────────────────────────────────┐               │
│  │                                                            │               │
│  │   ┌──────────┐     ┌──────────┐     ┌──────────┐          │               │
│  │   │   WAIT   │────▶│  CHECK   │────▶│  DECIDE  │          │               │
│  │   │ interval │     │ canary  │     │ train?   │          │               │
│  │   └──────────┘     └──────────┘     └────┬─────┘          │               │
│  │                                          │                │               │
│  │                                          ▼ NO             │               │
│  │                                    ┌──────────┐           │               │
│  │                                    │  CONTINUE│           │               │
│  │                                    │  Monitoring          │               │
│  │                                    └──────────┘           │               │
│  │                                          │                │               │
│  │                                          ▼ YES            │               │
│  │   ┌──────────┐     ┌──────────┐     ┌──────────┐          │               │
│  │   │ EVALUATE │◀────│  TRAIN   │◀────│  TRIGGER │          │               │
│  │   │  Canary  │     │  NEW     │     │  TRAINING│          │               │
│  │   └────┬─────┘     └──────────┘     └──────────┘          │               │
│  │        │                                                  │               │
│  │        ▼                                                  │               │
│  │   ┌──────────┐     ┌──────────┐     ┌──────────┐          │               │
│  │   │  GATE    │────▶│ PROMOTE  │────▶│  UPDATE  │          │               │
│  │   │  CHECK   │     │  or ROLL│     │  ACTIVE  │          │               │
│  │   └──────────┘     └──────────┘     └──────────┘          │               │
│  │                                                            │               │
│  │   ┌─────────────────────────────────────────────────────┐ │               │
│  │   │                    LOOP REPEATS                     │ │               │
│  │   └─────────────────────────────────────────────────────┘ │               │
│  │                                                            │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                                  │
│  Telegram Notifications:                                                        │
│  • Training start/end                                                         │
│  • Canary evaluation results                                                    │
│  • Promotion/rollback events                                                    │
│  • System health alerts                                                       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘


## Pipeline Trigger Methods

### Method 1: Manual (Per-Symbol)
```bash
# Train LSTM for specific symbol
python training/train_lstm.py

# Train PPO for specific symbol
python training/train_drl.py

# Evaluate and stage
python tools/champion_cycle.py
```

### Method 2: Autonomy Loop (Continuous)
```bash
# Start autonomy loop
python Python/autonomy_loop.py

# Environment variables
export AGI_AUTONOMY_INTERVAL_SEC=3600      # Check every hour
export AGI_AUTONOMY_TRAIN_EVERY_SEC=86400  # Train daily
export AGI_AUTONOMY_AUTO_CANARY=true       # Auto canary promotion
```

### Method 3: Champion Cycle (Batch)
```bash
# Run full cycle across all symbols
python tools/champion_cycle.py

# Single symbol
export AGI_CYCLE_SYMBOL=BTCUSDm
python tools/champion_cycle.py
```


## Key Files Reference

| File | Purpose | Lines |
|------|---------|-------|
| `training/train_lstm.py` | LSTM context training | 413 |
| `training/train_drl.py` | PPO policy training | 433 |
| `training/train_dreamer.py` | DreamerV3 world model | 200+ |
| `Python/model_evaluator.py` | Candidate evaluation | 150+ |
| `Python/model_registry.py` | Champion/Canary registry | 300+ |
| `Python/autonomy_loop.py` | Continuous training loop | 500+ |
| `tools/champion_cycle.py` | Batch training orchestrator | 200+ |
| `Python/hybrid_brain.py` | Live inference blending | 600+ |


## Environment Variables

```bash
# Feature Engineering
export AGI_FEATURE_VERSION=ultimate_150

# Training Control
export AGI_LSTM_SYMBOLS=BTCUSDm,EURUSDm
export AGI_DRL_SYMBOL=BTCUSDm
export AGI_TOTAL_TIMESTEPS=100000
export AGI_USE_SUBPROC_VECENV=1

# Autonomy
export AGI_AUTONOMY_INTERVAL_SEC=3600
export AGI_AUTONOMY_TRAIN_EVERY_SEC=86400
export AGI_AUTONOMY_AUTO_CANARY=true

# Canary Gates
export CANARY_MIN_TRADES=10
export CANARY_MAX_LOSS=75
export CANARY_MAX_DD=0.12
export AGI_GATE_MIN_SCORE_DELTA=0.25
```


## Data Flow Summary

```
MT5/Yahoo → DataFeed → FeaturePipeline → LSTM Training → LSTM Model
                                                    ↓
                                             TradingEnv → PPO Training → Candidate Model
                                                                           ↓
                                                                    ModelEvaluator → Gates
                                                                           ↓
                                                            ┌────────────┴────────────┐
                                                            ▼                         ▼
                                                      PROMOTE                        ROLLBACK
                                                            │                         │
                                                            ▼                         ▼
                                                      New Champion               Keep Old
                                                            │
                                                            ▼
                                                    Live Inference
                                                            │
                                                            ▼
                                                    Autonomy Loop
                                                            │
                                                            └─────────────────────────┘
                                                                     (REPEAT)
```

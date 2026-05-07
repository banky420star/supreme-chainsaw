# Guardian Trader Implementation

## Overview

Transformed `chain_gambler` from an "AI fortune teller" into a **Guardian Trader** — a process-driven, risk-first trading system that prioritizes capital preservation over prediction accuracy.

## Architecture

```
MarketGuardian
    ↓
MarketQuality Scorer (0-100)
    ↓
StrategySelector
    ↓
Entry Signal
    ↓
RiskEngine
    ↓
ExitEngine_R
    ↓
TradeJournal / Learning Loop
```

## New Modules Implemented

### 1. MarketGuardian (`Python/market_guardian.py`)

**Purpose**: Classify market regime before every trade

**Regimes Detected**:
- `LOW_VOL_RANGE` — Mean reversion only, small size
- `MED_VOL_TREND` — Trend following allowed
- `HIGH_VOL_BREAKOUT` — Momentum setups only
- `NEWS_SHOCK` — No new trades
- `SPREAD_DANGER` — No trading
- `CHOP` — No trading
- `NO_EDGE` — No trading

**Indicators Used**:
- ATR (14) — Volatility measurement
- ADX (14) — Trend strength
- RSI (14) — Overbought/oversold
- Bollinger Band width — Range compression/expansion

**Usage**:
```python
from Python.market_guardian import MarketGuardian

guardian = MarketGuardian(config)
regime = guardian.classify(df, symbol="XAUUSDm")

if regime.regime == MarketRegime.MED_VOL_TREND:
    # Allow trend following
    pass
```

### 2. MarketQualityScorer (`Python/market_guardian.py`)

**Purpose**: Calculate composite 0-100 quality score before every trade

**Component Weights**:
| Factor | Points | Description |
|--------|--------|-------------|
| No major news | 20 | EventGuard clearance |
| Spread normal | 15 | < 2.5 pips |
| Volatility tradable | 15 | Not chop/spread danger |
| Session liquid | 10 | London/NY session |
| Trend/range clear | 15 | Regime confidence > 70% |
| Reward:risk available | 10 | Minimum 1.5:1 R/R |
| No recent SL chop | 10 | < 2 recent stops |
| Model agrees | 5 | Confidence > 60% |

**Rules**:
- Score < 70: No trade
- Score 70-84: Half size only
- Score >= 85: Full size allowed

**Usage**:
```python
scorer = MarketQualityScorer(config)
quality = scorer.calculate(symbol, setup, regime, event_guard)

if quality.allowed:
    size_mult = scorer.get_position_size_multiplier(quality)
```

### 3. StrategySelector (`Python/strategy_selector.py`)

**Purpose**: Route trades to appropriate strategy module based on regime

**Strategy Modules**:

#### A. TrendModule
- **Applicable**: MED_VOL_TREND, HIGH_VOL_BREAKOUT
- **Entry**: Pullbacks to EMA (9/21)
- **Confidence**: Based on ADX

#### B. MeanReversionModule
- **Applicable**: LOW_VOL_RANGE
- **Entry**: RSI oversold/overbought + BB band touch
- **Target**: Mean (SMA 20)

#### C. BreakoutModule
- **Applicable**: HIGH_VOL_BREAKOUT
- **Entry**: Range compression + ATR expansion
- **Confirmation**: Volume/ATR spike

**Usage**:
```python
from Python.strategy_selector import StrategySelector

selector = StrategySelector(config)
context = StrategyContext(regime=regime, adx_14=30, ...)
signal = selector.generate_signal(symbol, df, context)
```

### 4. ExitEngine_R (`Python/exit_engine_r.py`)

**Purpose**: Professional R-multiple exit management

**R-Multiple Rules**:
| Level | Action | Description |
|-------|--------|-------------|
| 0.8R | Move to BE | Breakeven + small buffer |
| 1.0R | Close 33% | First scale out |
| 1.5R | Close 33% | Second scale out |
| 2.0R | Runner mode | Trailing stop activates |
| 4.0R | Close full | Max profit target |

**Additional Rules**:
- **Profit Retrace**: Close if profit retraces 35% from peak
- **Time Exit**: Close after 4 hours if < 0.5R
- **Trailing**: Runner trails 1R behind price

**Usage**:
```python
from Python.exit_engine_r import ExitEngineR

engine = ExitEngineR(config)
engine.register_position(pos_id, symbol, side, entry, stop, volume)

# Each tick:
action = engine.update_position(pos_id, current_price)
if action.volume_to_close > 0:
    executor.close(action.volume_to_close)
```

### 5. TradeJournal (`Python/trade_journal.py`)

**Purpose**: Post-trade learning and analysis

**Records per Trade**:
- Entry context (regime, strategy, spread, news distance)
- Risk metrics (initial R, stop, target)
- Outcome (PnL, R-multiple, max R reached)
- Exit reason and action

**Analytics**:
- Win rate by regime
- PnL by symbol/strategy
- Quality score effectiveness
- Exit action performance

**Recommendations**:
- Auto-generated based on performance data
- Example: "Focus on med_vol_trend regime (WR: 65%)"

**Usage**:
```python
from Python.trade_journal import TradeJournal

journal = TradeJournal(config)
journal.record_entry(trade_id, symbol, context)
journal.record_exit(trade_id, exit_price, pnl, reason)

insights = journal.analyze(lookback=50)
```

### 6. GuardianIntegration (`Python/guardian_integration.py`)

**Purpose**: Unified interface combining all components

**Main Methods**:
- `should_trade()` — Full Guardian check (regime + quality)
- `generate_signal()` — Strategy selection
- `register_position()` — Setup R-exits and journal
- `update_exit()` — Manage position exits
- `close_position()` — Complete trade record
- `get_insights()` — Learning analytics

**Usage**:
```python
from Python.guardian_integration import create_guardian_trader

guardian = create_guardian_trader("configs/guardian_trader_micro.yaml")

# Check if we should trade
decision = guardian.should_trade(symbol, df, setup)
if decision.allowed:
    signal = guardian.generate_signal(symbol, df)
    if signal.signal_type != SignalType.HOLD:
        # Execute trade
        trade_id = executor.execute(signal)
        guardian.register_position(trade_id, signal, decision)
```

## Configuration

### Micro Account Config (`configs/guardian_trader_micro.yaml`)

**Risk Settings**:
```yaml
risk:
  max_daily_loss: 2.0              # $2 (3.7%)
  max_trade_risk: 0.25             # $0.25 (0.46%)
  max_open_positions: 1            # Only 1 position
  max_lots: 0.01                   # Fixed 0.01 lots
  max_daily_trades: 5              # Max 5 trades/day
  stop_after_consecutive_losses: 3 # Stop after 3 SLs
```

**Event Guard**:
```yaml
event_guard:
  pre_event_min: 60               # Block 60 min before
  post_event_min: 45              # Block 45 min after
  extreme_pre_min: 180            # 3 hours for NFP/CPI/FOMC
```

**Exit Engine**:
```yaml
exit_engine_r:
  breakeven_trigger_r: 0.8
  scale_out_1_r: 1.0
  scale_out_2_r: 1.5
  runner_trigger_r: 2.0
  profit_retrace_pct: 0.35
  time_exit_minutes: 240
```

## Key Principles Implemented

### 1. No Trade is Better Than Bad Trade
- Default state: **NO TRADE**
- Must earn permission via quality score >= 70
- Regime filter blocks chop/spread danger/noise

### 2. Never Let Good Floating Profit Become Loss
- Breakeven at 0.8R
- Scale out 66% by 1.5R
- Runner mode with trailing
- Close on 35% retrace

### 3. Don't Predict News, Avoid It
- EventGuard: 60min before / 45min after
- Extreme events: 180min before / 90min after
- No trading during news shock regime

### 4. Model Suggests, Risk Decides, Exit Protects
- AGI/PPO provides signal
- MarketGuardian decides if tradable
- RiskEngine controls size
- ExitEngine_R manages position

### 5. Trade Fewer Setups With Better Conditions
- Quality score >= 70 required
- Half size for marginal setups (70-84)
- Time exit if trade goes nowhere

## Launcher Update

**Money_Printer_Launcher.bat** updated to v3.0:
- Guardian Trader components
- Tightened risk settings for $54 account
- Quality score minimum 70/100
- R-based exit engine

## Files Created

1. `Python/market_guardian.py` — Regime + Quality scorer
2. `Python/strategy_selector.py` — Strategy modules
3. `Python/exit_engine_r.py` — R-multiple exits
4. `Python/trade_journal.py` — Learning loop
5. `Python/guardian_integration.py` — Unified interface
6. `configs/guardian_trader_micro.yaml` — Micro account config
7. `GUARDIAN_TRADER_IMPLEMENTATION.md` — This documentation

## Integration Path

To integrate into `Server_AGI.py`:

```python
# Initialize (in __init__)
from Python.guardian_integration import create_guardian_trader
self.guardian = create_guardian_trader()

# In main loop
for symbol in self.symbols:
    df = self.get_data(symbol)

    # Guardian check
    decision = self.guardian.should_trade(symbol, df, setup)
    if not decision.allowed:
        logger.info(f"Guardian blocked {symbol}: {decision.reason}")
        continue

    # Generate signal
    signal = self.guardian.generate_signal(symbol, df)
    if signal.signal_type == SignalType.HOLD:
        continue

    # Execute
    trade_id = self.executor.execute(signal, size_mult=decision.position_size_mult)
    self.guardian.register_position(trade_id, signal, decision)

    # Update exits
    for pos_id, pos in self.positions.items():
        action = self.guardian.update_exit(pos_id, current_price)
        if action.volume_to_close > 0:
            self.executor.close_partial(pos_id, action)

    # Close complete
    if exit_condition:
        self.guardian.close_position(pos_id, exit_price, reason)
```

## Philosophy

> The better bot is less "AI fortune teller" and more **market sniper with a seatbelt, weather radar, and strict accountant**.

`chain_gambler` now embodies:
- **Process-driven** over prediction-driven
- **Capital preservation** over profit maximization
- **Risk-first** over return-first
- **Learning loop** for continuous improvement

This is the path from "clever bot that loses" to **boring bot that survives**.
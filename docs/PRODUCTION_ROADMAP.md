# Production Profitability Roadmap

## Phase 1: Foundation (Week 1)

### Day 1-2: Capital & Account Setup
**You need to do this - I can't do it for you:**

1. **Fund your trading account**
   - Minimum: $5,000 USD
   - Recommended: $10,000 USD
   - This is non-negotiable - you can't trade with $10

2. **Verify MT5 connection**
   ```bash
   python -c "import MetaTrader5 as mt5; print(mt5.initialize())"
   ```

3. **Test data feed access**
   ```bash
   python Python/data_feed.py --test-connection
   ```

### Day 3-4: Enhanced Training

**Run multi-timeframe optimization training:**

```bash
# Train all configured symbols with timeframe optimization
python start_enhanced_training.py \
  --symbols BTCUSDm,XAUUSDm,EURUSDm,GBPUSDm \
  --timeframe-opt \
  --per-symbol-metrics \
  --live
```

**What this does:**
- Tests M1, M5, M15, M30, H1 for each symbol
- Selects best timeframe based on Sharpe ratio
- Tracks per-symbol profit/loss, drawdown, win rate
- Saves results to `logs/enhanced_training_results_*.json`

**Success criteria:**
- All symbols complete training without errors
- Best timeframe selected for each symbol
- Training report generated

### Day 5-7: Backtest Validation

**Run comprehensive backtest:**

```bash
python backtester.py \
  --symbols BTCUSDm,XAUUSDm,EURUSDm,GBPUSDm \
  --period "2y" \
  --timeframe auto \
  --feature-version ultimate_150 \
  --output logs/backtest_production.json
```

**Analyze results:**

```python
# Check if backtest shows profitability
python -c "
import json
with open('logs/backtest_production.json') as f:
    results = json.load(f)

print(f\"Total Return: {results['total_return_pct']:.2f}%\")
print(f\"Sharpe Ratio: {results['sharpe_ratio']:.2f}\")
print(f\"Max Drawdown: {results['max_drawdown_pct']:.2f}%\")
print(f\"Win Rate: {results['win_rate']:.1f}%\")
print(f\"Total Trades: {results['total_trades']}\")
print(f\"Profit Factor: {results['profit_factor']:.2f}\")

# Production criteria check
if results['sharpe_ratio'] > 1.0:
    print('✅ Sharpe ratio OK')
else:
    print('❌ Sharpe ratio too low - need > 1.0')

if results['max_drawdown_pct'] < 15:
    print('✅ Drawdown OK')
else:
    print('❌ Drawdown too high - need < 15%')

if results['total_trades'] > 100:
    print('✅ Sample size OK')
else:
    print('❌ Not enough trades')
"
```

**Gate checkpoint:**
- ❌ If Sharpe < 1.0 or drawdown > 15%: STOP. Fix model before proceeding.
- ✅ If all criteria met: Proceed to Phase 2

---

## Phase 2: Paper Trading (Weeks 2-3)

### Week 2: Paper Trading Setup

**Configure paper trading mode:**

```bash
# Create paper trading config
cat > config_paper.yaml << 'EOF'
trading:
  mode: PAPER
  symbols:
    - BTCUSDm
    - XAUUSDm
    - EURUSDm
    - GBPUSDm
  initial_balance: 10000
  risk_per_trade: 0.01  # 1% risk per trade
  
risk:
  max_daily_loss_pct: 3
  max_drawdown_pct: 10
  max_positions_per_symbol: 2
  max_total_positions: 5

mt5:
  # Your MT5 demo/paper account credentials
  login: ${MT5_DEMO_LOGIN}
  password: ${MT5_DEMO_PASSWORD}
  server: ${MT5_DEMO_SERVER}
EOF
```

**Start paper trading:**

```bash
export AGI_LIVE_ENABLED=false
export AGI_PAPER_MODE=true
export AGI_DAILY_RISK_LIMIT=3.0

python start_live.py --config config_paper.yaml --paper
```

**Monitor via dashboard:**
- Open http://localhost:4180
- Check "Trading" tab for paper positions
- Verify no real money at risk

### Week 3: Data Collection & Analysis

**Daily monitoring:**

```bash
# Run this daily to check paper trading performance
python -c "
from Python.trade_review import get_latest_review
review = get_latest_review()

print('=== Paper Trading Performance ===')
print(f\"Trades: {review['summary']['total_trades']}\")
print(f\"Win Rate: {review['summary']['win_rate']:.1f}%\")
print(f\"PnL: \${review['summary']['total_pnl']:.2f}\")
print(f\"Profit Factor: {review['summary']['profit_factor']:.2f}\")
print(f\"Avg Win: \${review['summary']['avg_win']:.2f}\")
print(f\"Avg Loss: \${review['summary']['avg_loss']:.2f}\")

# Daily check
if review['summary']['total_pnl'] > 0:
    print('✅ Profitable day')
else:
    print('⚠️ Loss day - review trades')
"
```

**Required sample size:**
- Minimum 50 trades (2 weeks)
- Preferred 100+ trades (3-4 weeks)

**Gate checkpoint:**
- ❌ If win rate < 50% or profit factor < 1.2 after 50 trades: STOP. Retrain models.
- ✅ If profitable with win rate > 50%: Proceed to Phase 3

---

## Phase 3: Micro-Live Trading (Weeks 4-6)

### Week 4: Live Micro-Lots

**Start with smallest possible positions:**

```bash
export AGI_LIVE_ENABLED=true
export AGI_REQUIRE_EXPLICIT_LIVE_ARM=true
export AGI_RISK_PERCENT=0.5  # 0.5% risk per trade (ultra conservative)
export AGI_MIN_LOTS=0.01
export AGI_MAX_LOTS=0.02  # Max 0.02 lots
export AGI_MAX_POS_PER_SYMBOL=1  # Only 1 position per symbol
export AGI_MAX_TOTAL_POS=3  # Max 3 positions total

python start_live.py --live
```

**Verify live mode in UI:**
- Dashboard should show "LIVE" indicator in red
- Confirm real positions appearing in MT5
- Check P&L is updating

### Week 5-6: Gradual Scale-Up

**If profitable after week 4:**

```bash
# Increase risk slightly
export AGI_RISK_PERCENT=1.0  # 1% risk per trade
export AGI_MAX_LOTS=0.05
export AGI_MAX_POS_PER_SYMBOL=2
export AGI_MAX_TOTAL_POS=5
```

**Daily P&L tracking:**

```bash
# Run this end of each trading day
python -c "
import json
import glob
from datetime import datetime

# Get today's trades
today = datetime.now().strftime('%Y-%m-%d')
logs = glob.glob(f'logs/trade_events_{today}*.jsonl')

total_pnl = 0
wins = 0
losses = 0

for log in logs:
    with open(log) as f:
        for line in f:
            event = json.loads(line)
            if event.get('event') == 'trade_closed':
                pnl = event['payload'].get('profit', 0)
                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

total = wins + losses
wr = (wins / total * 100) if total > 0 else 0

print(f'=== {today} Live Trading ===')
print(f'Trades: {total} ({wins}W/{losses}L)')
print(f'Win Rate: {wr:.1f}%')
print(f'P&L: \${total_pnl:.2f}')
print(f'Drawdown: Check dashboard')

# Phase 3 gate
if total >= 20 and total_pnl > 0:
    print('✅ Phase 3 complete - ready to scale')
else:
    print('⚠️ Need more data or review performance')
"
```

---

## Phase 4: Production Scale (Month 2+)

### Scale-Up Criteria
**Only proceed if ALL of these are met:**
1. ✅ 100+ live trades completed
2. ✅ Win rate > 55%
3. ✅ Profit factor > 1.5
4. ✅ Max drawdown < 10%
5. ✅ Sharpe ratio > 1.0
6. ✅ 2 consecutive profitable weeks

### Production Configuration

```bash
# Full production settings
export AGI_RISK_PERCENT=2.0  # 2% risk per trade (standard)
export AGI_MAX_LOTS=0.5
export AGI_MAX_POS_PER_SYMBOL=3
export AGI_MAX_TOTAL_POS=8
export AGI_TRAIL_INTERVAL_SEC=15
export AGI_HEDGING_ENABLED=true
export AGI_TREND_FLIP_ENABLED=true
```

---

## Risk Management Checkpoints

### Emergency Stop Triggers
**Immediately stop trading if:**
- Daily loss exceeds 3%
- Drawdown exceeds 10%
- 5 consecutive losing trades
- Win rate drops below 45% over 20 trades
- Any single trade loses > 2% of account

### Weekly Review Process
Every Sunday:
1. Review all trades from past week
2. Calculate actual performance metrics
3. Compare to backtest expectations
4. Adjust position sizes if needed
5. Retrain models if performance degrading

---

## Quick Reference Commands

### Check Live Performance
```bash
# Real-time dashboard
curl http://localhost:5000/api/status | python -m json.tool

# Trade review
curl http://localhost:5000/api/trade_review | python -m json.tool

# Training metrics
curl http://localhost:5000/api/training/metrics | python -m json.tool

# Health check
curl http://localhost:5000/api/health
```

### Emergency Stop
```bash
# Via API
curl -X POST http://localhost:5000/api/control \
  -H "Content-Type: application/json" \
  -d '{"action": "emergency_stop"}'

# Via UI
# Click "Emergency Stop" button on Control screen
```

### View Logs
```bash
# Real-time trade log
tail -f logs/trade_events.jsonl

# Training progress
tail -f logs/ppo_training.log

# Server errors
tail -f logs/server.log

# Decisions
tail -f logs/decisions.jsonl
```

---

## Success Metrics

| Metric | Phase 1 Target | Phase 2 Target | Phase 3 Target | Production |
|--------|---------------|----------------|----------------|------------|
| Sharpe Ratio | > 1.0 | > 1.0 | > 1.2 | > 1.5 |
| Win Rate | Backtest only | > 50% | > 55% | > 60% |
| Profit Factor | > 1.5 | > 1.3 | > 1.5 | > 2.0 |
| Max Drawdown | < 15% | < 10% | < 8% | < 5% |
| Trades/Week | N/A | 20-30 | 30-50 | 50+ |
| Avg Trade | N/A | > 0 | > $5 | > $20 |

---

## Common Failure Points

### ❌ "I can't fund $5,000"
**Reality check:** You can't trade forex/gold professionally with less. Options:
1. Save up minimum $1,000 for micro-lots only
2. Trade on demo/paper until you have capital
3. Use prop firm challenge accounts (FTMO, etc.)

### ❌ "Backtests look good but paper trading loses"
**Problem:** Overfitting to historical data
**Solution:** 
- Use walk-forward analysis
- Reduce model complexity
- Increase regularization
- Add more validation data

### ❌ "Paper trades win but live trades lose"
**Problem:** Slippage, spread, execution delays
**Solution:**
- Reduce position sizes
- Add execution delay buffer
- Use limit orders instead of market orders
- Avoid high-spread times (news events)

### ❌ "System works for weeks then blows up"
**Problem:** Market regime change
**Solution:**
- Monitor regime detection
- Reduce size during unknown regimes
- Add circuit breakers
- Weekly model retraining

---

## Next Actions (Do These Now)

1. **Fund account** - $5,000 minimum
2. **Run enhanced training** - Command above
3. **Verify MT5 connection** - Test data feed
4. **Start paper trading** - Week 2 plan
5. **Collect 100 trades** - Minimum for validation

**Estimated time to production:** 4-6 weeks if profitable, 3+ months if models need retraining.

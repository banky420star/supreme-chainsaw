# Chain Gambler Go-Live Checklist

## Pre-Live Validation Process

This checklist ensures the bot is ready for live trading. **Do not skip steps**.

---

## Phase 1: Backtesting (Week 1)

### 1.1 Data Preparation
- [ ] Download 6+ months of historical data for all symbols
- [ ] Verify data quality (no gaps, correct timestamps)
- [ ] Test with multiple timeframes (M5, M15, H1)

### 1.2 Run Comprehensive Backtest

```bash
# Run 6-month backtest
python Python/backtest_engine.py \
    --symbols EURUSDm GBPUSDm XAUUSDm BTCUSDm \
    --days 180 \
    --equity 10000.0 \
    --output full_backtest_6m
```

### 1.3 Backtest Validation Criteria

| Metric | Minimum | Target | Status |
|--------|---------|--------|--------|
| Total Trades | >100 | >200 | ⬜ |
| Win Rate | >40% | >48% | ⬜ |
| Profit Factor | >1.2 | >1.5 | ⬜ |
| Sharpe Ratio | >0.8 | >1.2 | ⬜ |
| Max Drawdown | <25% | <18% | ⬜ |
| Expectancy | >$1 | >$3 | ⬜ |
| Avg Signal Quality | >0.60 | >0.70 | ⬜ |

**All minimum criteria must be met before proceeding.**

### 1.4 Backtest Analysis

```bash
# Generate monitoring analysis
python Python/monitoring_dashboard.py \
    --mode backtest \
    --file backtests/full_backtest_6m/trades.csv
```

- [ ] Verify signal quality trend is stable or improving
- [ ] Check Kelly sizing effectiveness by bucket
- [ ] Analyze performance by symbol
- [ ] Review trade distribution (best/worst hours)
- [ ] Confirm no excessive concentration in single symbol

### 1.5 Walk-Forward Validation

- [ ] Run rolling 30-day backtests across the 6-month period
- [ ] Verify performance is consistent (not overfit to specific period)
- [ ] Check for performance degradation in recent months
- [ ] Confirm strategy works in different market regimes

---

## Phase 2: Paper Trading (Week 2-3)

### 2.1 Setup Paper Trading

```bash
# Start paper trading with Ollama oversight
python Python/paper_trader.py \
    --symbols EURUSDm GBPUSDm XAUUSDm \
    --equity 10000.0 \
    --cycles 1000
```

### 2.2 Daily Monitoring

**Each day, verify:**

- [ ] No critical errors in logs
- [ ] Signal quality scores are reasonable (>0.60 avg)
- [ ] Kelly sizing is being applied
- [ ] Drawdown stays within limits (<5% daily)
- [ ] Trade frequency is as expected
- [ ] Ollama reviews are being generated

### 2.3 Weekly Review

**After 7 days:**

- [ ] Generate weekly performance report
- [ ] Compare to backtest results (should be within 20%)
- [ ] Review Ollama recommendations
- [ ] Check for any degrading performance

### 2.4 Paper Trading Success Criteria

| Metric | Minimum | Status |
|--------|---------|--------|
| Win Rate | Within 5% of backtest | ⬜ |
| Avg Trade | Within 10% of backtest | ⬜ |
| Max Drawdown | <10% | ⬜ |
| Signal Quality | >0.60 | ⬜ |
| System Uptime | >95% | ⬜ |

---

## Phase 3: Risk System Validation

### 3.1 Kill Switch Testing

Test each kill switch scenario:

```python
# Test daily loss kill switch
risk.record_pnl(-500)  # Exceed daily limit
assert risk.halt == True
assert risk._halt_reason == "daily_loss"

# Test consecutive errors
for _ in range(3):
    risk.record_error(critical=True)
assert risk.halt == True
assert risk._halt_reason == "consecutive_errors"

# Test max drawdown
risk._current_equity = 7500  # 25% drawdown
risk.can_trade("EURUSDm")  # Should set halt
assert risk.halt == True
assert risk._halt_reason == "max_drawdown"
```

- [ ] Daily loss kill switch triggers correctly
- [ ] Hourly loss kill switch triggers correctly
- [ ] Consecutive errors kill switch triggers correctly
- [ ] Max drawdown kill switch triggers correctly
- [ ] Kill switches can be manually cleared by operator

### 3.2 Symbol Validation

- [ ] Path traversal attempts are blocked
- [ ] Invalid symbols are rejected
- [ ] Only whitelisted symbols can trade

### 3.3 API Security

- [ ] Control token is required for protected actions
- [ ] CORS only allows whitelisted origins
- [ ] Rate limiting is active

---

## Phase 4: Live Deployment Preparation

### 4.1 Environment Setup

```bash
# Set conservative parameters
export AGI_MIN_QUALITY_SCORE=0.70
export AGI_KELLY_FRACTION=0.3
export AGI_DEADZONE_CONFIDENCE=0.99
export AGI_BIAS_STRENGTH=0.2
export AGI_IS_LIVE=1

# Security
export AGI_CONTROL_TOKEN="your_secure_random_token"
export AGI_ALLOWED_ORIGINS="https://yourdomain.com"
```

### 4.2 Account Setup

- [ ] MT5 account is funded
- [ ] VPS is stable (99.9% uptime)
- [ ] Internet connection is reliable
- [ ] Backup power/internet available
- [ ] Telegram alerts are configured
- [ ] Emergency contact procedures documented

### 4.3 Position Sizing

- [ ] Start with 50% of intended risk per trade
- [ ] Max portfolio heat set to 4% (conservative)
- [ ] Per-symbol heat capped at 2%
- [ ] Daily loss limit at 2% of equity

### 4.4 Monitoring Setup

- [ ] Dashboard is accessible
- [ ] Logs are being written
- [ ] Alerts are configured
- [ ] Ollama advisor is enabled
- [ ] Daily report generation is active

---

## Phase 5: Live Trading Launch

### 5.1 Soft Launch (Day 1-3)

- [ ] Trade with 50% size for first 3 days
- [ ] Monitor every 2 hours
- [ ] Verify all trades are being logged
- [ ] Check signal quality scores
- [ ] Confirm Kelly sizing is working

### 5.2 Gradual Scale-Up

**If soft launch successful:**

- [ ] Day 4-7: Scale to 75% size
- [ ] Day 8+: Full size (if metrics hold)

### 5.3 Daily Operations

**Each trading day:**

- [ ] Review pre-market Ollama analysis
- [ ] Check overnight positions
- [ ] Monitor drawdown throughout day
- [ ] Review daily performance report
- [ ] Note any anomalies or errors

---

## Phase 6: Ongoing Validation

### 6.1 Weekly Reviews

**Every Sunday:**

- [ ] Generate weekly performance report
- [ ] Compare to benchmarks
- [ ] Review signal quality trends
- [ ] Check Kelly effectiveness
- [ ] Analyze symbol performance
- [ ] Update strategy if needed

### 6.2 Monthly Deep Dive

**Every month:**

- [ ] Full performance attribution analysis
- [ ] Correlation matrix update
- [ ] Strategy parameter review
- [ ] Risk limit calibration
- [ ] Ollama strategy review

### 6.3 Performance Degradation Triggers

**Immediate review if:**

- [ ] Win rate drops below 35% for 2 weeks
- [ ] Sharpe ratio falls below 0.5
- [ ] Drawdown exceeds 20%
- [ ] Signal quality degrades below 0.55
- [ ] Profit factor falls below 1.1

---

## Emergency Procedures

### Emergency Stop

```python
# Immediate halt via API
curl -X POST http://localhost:5000/api/control \
    -H "Content-Type: application/json" \
    -H "X-Control-Token: $AGI_CONTROL_TOKEN" \
    -d '{"action": "emergency_stop"}'
```

### Kill Switch Override

Only in emergencies:
- Clear halt when underlying issue is fixed
- Document reason for override
- Reduce position sizes after override

### Rollback Procedure

If optimizations are causing issues:
1. Switch to `champion` model (not canary)
2. Disable Kelly sizing: `AGI_KELLY_FRACTION=1.0`
3. Raise quality threshold: `AGI_MIN_QUALITY_SCORE=0.80`
4. Contact developer if issues persist

---

## Sign-Off

**Before going live, both parties must sign:**

### Trader Acknowledgment

I understand that:
- [ ] This is a high-risk trading system
- [ ] Past performance does not guarantee future results
- [ ] I could lose my entire trading capital
- [ ] I have tested the system thoroughly
- [ ] I understand the emergency procedures
- [ ] I will monitor the system daily

**Trader Signature:** _________________ **Date:** _______

### Developer Acknowledgment

I confirm that:
- [ ] All critical bugs have been fixed
- [ ] The system has passed all validation tests
- [ ] Documentation is complete
- [ ] Support procedures are in place
- [ ] The system is ready for live trading

**Developer Signature:** _________________ **Date:** _______

---

## Quick Reference

### Key Commands

```bash
# Start live trading
python Python/Server_AGI.py --live

# Start paper trading
python Python/paper_trader.py --symbols EURUSDm GBPUSDm XAUUSDm

# Run backtest
python Python/backtest_engine.py --symbols EURUSDm --days 90

# View monitoring dashboard
python Python/monitoring_dashboard.py

# Check Ollama health
curl http://localhost:11434/api/tags
```

### Key Metrics

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| Win Rate | >45% | 35-45% | <35% |
| Sharpe | >1.0 | 0.5-1.0 | <0.5 |
| Max DD | <15% | 15-20% | >20% |
| Sig Quality | >0.65 | 0.55-0.65 | <0.55 |
| Profit Factor | >1.3 | 1.1-1.3 | <1.1 |

### Emergency Contacts

- Developer: _________________
- Broker Support: _________________
- VPS Provider: _________________

---

**Remember: No trading system is perfect. Trade only with capital you can afford to lose.**

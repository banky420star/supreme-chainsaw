"""
Best Feature Configuration for XAUUSDm (found via micro-adjustment search on 10k 1m bars)
Multi-timeframe: 1m + 5m + 15m + 1h

Use this as the new default for XAU experiments and training.
"""

XAUUSDm_BEST_FEATURE_PARAMS = {
    "sma_fast": 12,
    "sma_slow": 40,
    "ema_fast": 8,
    "ema_slow": 21,
    "rsi_period": 21,
    "atr_period": 10,
    "higher_tf_vol_lookback": 30,
}

print("Best micro-adjusted feature parameters for XAUUSDm:")
for k, v in XAUUSDm_BEST_FEATURE_PARAMS.items():
    print(f"  {k}: {v}")

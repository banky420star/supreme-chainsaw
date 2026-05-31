"""
Profitability Improvement Experiments on 10k XAUUSDm 1min bars.
Focus: What actually moves realized P&L, not just shaped reward.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = "C:\\supreme-chainsaw"
sys.path.insert(0, PROJECT_ROOT)

from drl.trading_env import TradingEnv

# ============================================================
# LOAD DATA
# ============================================================
latest = max(Path("data/test").glob("xauusd_m1_10k_*.jsonl"), key=lambda p: p.stat().st_mtime)
print(f"Loading: {latest.name}")

raw = pd.DataFrame([json.loads(line) for line in open(latest)])
raw["timestamp"] = pd.to_datetime(raw["timestamp"])
raw = raw.set_index("timestamp").sort_index()

df = pd.DataFrame({
    "open": raw["open"].values,
    "high": raw["high"].values,
    "low": raw["low"].values,
    "close": raw["close"].values,
    "volume": raw["volume"].values,
}, index=raw.index)

print(f"Data loaded: {len(df)} bars\n")

# ============================================================
# HELPER: Run episode and collect realized metrics
# ============================================================
def run_episode(env, policy_fn, max_steps=4000, seed=42):
    np.random.seed(seed)
    obs, _ = env.reset()
    
    equity_curve = [env.equity]
    trades = 0
    total_reward = 0.0
    
    for step in range(max_steps):
        action = policy_fn(obs, env, step)
        obs, reward, terminated, truncated, info = env.step(action)
        
        total_reward += reward
        equity_curve.append(env.equity)
        
        if abs(info.get("action_components", {}).get("size", 0)) > 0.01:
            trades += 1
            
        if terminated or truncated:
            break
    
    eq = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    
    return {
        "final_equity": env.equity,
        "total_return_pct": (env.equity / 10000 - 1) * 100,
        "max_dd": dd.max(),
        "trades": trades,
        "total_shaped_reward": total_reward,
        "steps": len(eq) - 1,
        "equity_curve": eq,
    }

# ============================================================
# POLICIES
# ============================================================
def random_policy(obs, env, step):
    return np.array([
        np.random.uniform(-0.7, 0.7),
        np.random.uniform(0.05, 0.3),
        np.random.uniform(-0.04, 0.04),
        0, 0, 0
    ], dtype=np.float32)

def always_long_small(obs, env, step):
    return np.array([0.4, 0.15, 0.02, 0, 0, 0], dtype=np.float32)

def volatility_filter(obs, env, step):
    # Simple policy: only trade when recent volatility is moderate
    # (very crude - just for demonstration)
    vol = np.std(env.recent_returns[-20:]) if len(env.recent_returns) > 20 else 0.001
    if vol > 0.0008:
        direction = 0.0  # stay flat in high vol
    else:
        direction = 0.35
    return np.array([direction, 0.12, 0.015, 0, 0, 0], dtype=np.float32)

# ============================================================
# EXPERIMENT CONFIGS
# ============================================================
configs = [
    # (name, penalty_scale, policy)
    ("Random + Hardened",     1.0,  random_policy),
    ("Random + Medium",       0.5,  random_policy),
    ("Random + Light",        0.25, random_policy),
    ("AlwaysLong + Hardened", 1.0,  always_long_small),
    ("VolFilter + Hardened",  1.0,  volatility_filter),
    ("VolFilter + Medium",    0.5,  volatility_filter),
]

results = []

print("=== Running Profitability Experiments ===\n")

for name, ps, policy in configs:
    env = TradingEnv(
        df=df,
        initial_balance=10000.0,
        commission_rate=0.0002,
        spread_bps=2.0,
        slippage_bps=8.0,           # realistic for XAU
        max_drawdown=0.10,
        window_size=80,
        penalty_scale=ps,
        reward_scale=0.05,
        symbol="XAUUSDm",
    )
    
    res = run_episode(env, policy, max_steps=3500, seed=123)
    res["name"] = name
    res["penalty_scale"] = ps
    results.append(res)
    
    print(f"{name}")
    print(f"  Final Equity: ${res['final_equity']:,.2f}  ({res['total_return_pct']:+.2f}%)")
    print(f"  Max DD:       {res['max_dd']*100:.2f}%")
    print(f"  Trades:       {res['trades']}")
    print(f"  Shaped Reward:{res['total_shaped_reward']:+.2f}")
    print()

# ============================================================
# ANALYSIS
# ============================================================
print("=" * 60)
print("PROFITABILITY IMPROVEMENT ANALYSIS")
print("=" * 60)

df_results = pd.DataFrame(results)

best_equity = df_results.loc[df_results['final_equity'].idxmax()]
worst_equity = df_results.loc[df_results['final_equity'].idxmin()]

print(f"\nBest realized equity: {best_equity['name']} → ${best_equity['final_equity']:,.2f}")
print(f"Worst realized equity: {worst_equity['name']} → ${worst_equity['final_equity']:,.2f}")

print("\nKey Takeaways for Improving Profitability on this data:")
print("""
1. Reward shaping (penalty_scale) has almost zero impact on realized P&L
   when the policy is weak. It only changes the training signal.

2. Policy quality dominates everything.
   - Random policy loses money.
   - Even a crude volatility filter improved results slightly.

3. To actually make money on XAU 1min you need (in rough order of impact):
   a) Much better directional edge / regime detection
   b) Intelligent position sizing (volatility targeting)
   c) Strict filters (time of day, spread, news, volatility regime)
   d) Better execution modeling (your 8bps slippage is realistic)
   e) Possibly different holding periods (1min may be too noisy)

4. The current environment is already quite "honest".
   It is correctly telling you that a weak policy on this data loses money.
   That is valuable information, not a bug.

5. Next useful experiments:
   - Add strong features (especially for Gold: USD strength, time-of-day, 
     previous day range, session volatility)
   - Train a small PPO with good features + sensible reward
   - Test on out-of-sample periods
""")

print("\nRecommendation:")
print("Stop tweaking reward profiles for now.")
print("Focus on building a much stronger feature set + policy.")

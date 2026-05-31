"""Test different reward profiles on the 10k XAUUSDm M1 dataset."""
import os
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = "C:\\supreme-chainsaw"
sys.path.insert(0, PROJECT_ROOT)

from drl.trading_env import TradingEnv

# Load our test data
latest = max(Path("data/test").glob("xauusd_m1_10k_*.jsonl"), key=lambda p: p.stat().st_mtime)
print(f"Loading test data: {latest.name}")

raw = pd.DataFrame([json.loads(line) for line in open(latest)])
raw["timestamp"] = pd.to_datetime(raw["timestamp"])
raw = raw.set_index("timestamp").sort_index()

# Prepare minimal OHLCV DataFrame expected by TradingEnv
df = pd.DataFrame({
    "open": raw["open"].values,
    "high": raw["high"].values,
    "low": raw["low"].values,
    "close": raw["close"].values,
    "volume": raw["volume"].values,
}, index=raw.index)

print(f"Data prepared: {len(df)} bars")

def run_episode(penalty_scale: float, max_steps: int = 3000, seed: int = 42):
    """Run one episode with a given penalty_scale and record metrics."""
    env = TradingEnv(
        df=df,
        initial_balance=10000.0,
        commission_rate=0.0002,
        spread_bps=2.0,
        slippage_bps=8.0,           # realistic for XAU
        max_drawdown=0.12,
        window_size=100,
        penalty_scale=penalty_scale,
        reward_scale=0.1,           # keep magnitude reasonable for comparison
        symbol="XAUUSDm",
    )
    
    np.random.seed(seed)
    obs, _ = env.reset()
    
    total_reward = 0.0
    equities = [env.equity]
    trades = 0
    
    for step in range(max_steps):
        # Simple policy: small random actions (direction + size)
        action = np.array([
            np.random.uniform(-0.6, 0.6),   # direction
            np.random.uniform(0.05, 0.25),  # size
            np.random.uniform(-0.03, 0.03), # target
            0.0, 0.0, 0.0
        ], dtype=np.float32)
        
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        equities.append(env.equity)
        
        if info.get("action_components", {}).get("size", 0) > 0.01:
            trades += 1
            
        if terminated or truncated:
            break
    
    eq_curve = np.array(equities)
    peak = np.maximum.accumulate(eq_curve)
    dd = (peak - eq_curve) / peak
    max_dd = dd.max()
    
    return {
        "penalty_scale": penalty_scale,
        "total_reward": total_reward,
        "final_equity": env.equity,
        "max_drawdown": max_dd,
        "steps": len(eq_curve) - 1,
        "trades": trades,
        "avg_reward_per_step": total_reward / max(1, len(eq_curve)-1),
    }

print("\n=== Evaluating Reward Profiles on XAUUSDm M1 ===")
profiles = [
    ("Hardened (default)", 1.0),
    ("Medium", 0.5),
    ("Light (early training)", 0.25),
]

results = []
for name, ps in profiles:
    res = run_episode(penalty_scale=ps, max_steps=2500)
    res["name"] = name
    results.append(res)
    print(f"\n{name} (penalty_scale={ps}):")
    print(f"  Total reward      : {res['total_reward']:+.2f}")
    print(f"  Final equity      : ${res['final_equity']:,.2f}")
    print(f"  Max DD experienced: {res['max_drawdown']*100:.2f}%")
    print(f"  Trades taken      : {res['trades']}")
    print(f"  Avg reward/step   : {res['avg_reward_per_step']:+.5f}")

print("\n=== Key Insights for Profitability ===")
print("Light profiles produce much higher (less negative) shaped rewards")
print("because drawdown and cost penalties are heavily down-weighted.")
print("However, the *realized equity curve* (final_equity / max_dd) is what actually matters for live trading.")
print("The gap between shaped reward and realized P&L is exactly why post-alignment gates use equity metrics, not training reward.")

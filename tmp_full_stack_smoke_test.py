#!/usr/bin/env python3
"""
Full Stack Smoke Test for Decision PPO + Timing/News + MTF + Loop readiness.
Tests the major pieces we've built and integrated.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

print("=" * 70)
print("FULL STACK SMOKE TEST - Decision PPO + Timing/News/Open + MTF + Autonomy")
print("=" * 70)

errors = []
passes = []

def test(name, fn):
    try:
        fn()
        print(f"[PASS] {name}")
        passes.append(name)
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
        errors.append((name, str(e)))

# 1. Data feed MTF + local cache (the recent fix)
def test_data_mtf():
    from Python.data_feed import fetch_multitimeframe_training_data
    data = fetch_multitimeframe_training_data("XAUUSDm", period="7d", bars=500)
    assert isinstance(data, dict)
    assert "1m" in data or any(k in data for k in ["1m","5m","15m","1h"])
    print(f"  Got {len(data)} TFs for XAU (best available)")

test("Data MTF + XAU cache fallback (data reliability fix)", test_data_mtf)

# 2. Feature builder with new session/news timing features
def test_features_timing():
    import pandas as pd
    from Python.features.build_features import FeatureBuilder
    df = pd.DataFrame({
        'time': pd.date_range('2025-01-01', periods=100, freq='1min', tz='UTC'),
        'open': 4400.0, 'high': 4401.0, 'low': 4399.0, 'close': 4400.5, 'volume': 100
    })
    fb = FeatureBuilder()
    feats = fb.build(df)
    assert 'major_open_window' in feats
    assert 'news_proximity' in feats
    assert 'hour_sin' in feats
    print("  Timing features present: major_open_window, news_proximity, hour_sin/cos, etc.")

test("Feature builder - session/open + news timing features", test_features_timing)

# 3. Reward timing shaping
def test_reward_timing():
    from Python.rewards.reward_function import TradingReward
    r = TradingReward()
    out = r.compute(10000, 10050, 0.0, 0.01, 4400, 4399, 0.01, hold_steps=10, risk_used=0.005,
                    news_proximity=0.9, major_open_window=1.0, news_avoidance_zone=1.0)
    assert 'reward' in out
    print(f"  Reward with timing signals: {out['reward']:.6f}")

test("Reward function - timing/news/open bonuses/penalties", test_reward_timing)

# 4. TradeDecision TimeExitSpec for news/opens (core of user's request)
def test_trade_decision_timing():
    from Python.execution.trade_decision import TradeDecision, TimeExitSpec
    td = TradeDecision(
        symbol="XAUUSDm", side="LONG",
        time_exit=TimeExitSpec(close_before_high_impact_news=True, close_at_session_end=True)
    )
    d = td.to_dict()
    assert d['time_exit']['close_before_high_impact_news'] is True
    print("  Rich TimeExitSpec for news/session present and serializable")

test("TradeDecision - TimeExitSpec for news and market open handling", test_trade_decision_timing)

# 5. Timing analyzer (user's requested visibility)
def test_timing_analyzer():
    from Python.analysis.trade_timing_analyzer import analyze_profitable_trade_timing
    res = analyze_profitable_trade_timing(top_n=5)
    assert isinstance(res, dict)
    print(f"  Analyzer returns dict (journal may be empty: { 'error' in res })")

test("Trade timing analyzer (profitable trades + opens + news)", test_timing_analyzer)

# 6. Decision PPO env creation with action_config
def test_decision_ppo_env():
    from drl.trading_env import TradingEnv
    import pandas as pd
    import numpy as np
    df = pd.DataFrame({
        'time': pd.date_range('2025-01-01', periods=200, freq='1min', tz='UTC'),
        'open': 4400.0, 'high': 4401.0, 'low': 4399.0, 'close': 4400.5, 'volume': 100
    })
    env = TradingEnv(df, action_config={"decision_ppo": True, "decision_action_dim": 18})
    assert env.decision_ppo
    obs, _ = env.reset()
    action = np.random.uniform(-1,1,18).astype(np.float32)
    obs, r, term, trunc, info = env.step(action)
    print(f"  Decision PPO env step OK, reward={r:.4f}, decision_ppo=True")

test("TradingEnv with decision_ppo=True + 18-dim rich action", test_decision_ppo_env)

print("\n" + "=" * 70)
print(f"SUMMARY: {len(passes)} passed, {len(errors)} failed")
if errors:
    for name, err in errors:
        print(f"  - {name}: {err}")
print("=" * 70)

if errors:
    sys.exit(1)
else:
    print("Core stack smoke tests PASSED. Ready for deeper agent-driven validation + 100% push.")

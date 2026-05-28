#!/usr/bin/env python3
"""
Quick CLI for the new high-speed backtester.

Example:
    python scripts/run_fast_backtest.py --symbol XAUUSDm --weeks 4 --speed fast
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from Python.backtest.fast_backtester import FastBacktester, BacktestConfig


def main():
    parser = argparse.ArgumentParser(description="Fast Backtester for Supreme Chainsaw")
    parser.add_argument("--symbol", default="XAUUSDm")
    parser.add_argument("--weeks", type=int, default=2, help="How many weeks of data to simulate")
    parser.add_argument("--speed", choices=["fast", "realistic"], default="fast")
    parser.add_argument("--use-patterns", action="store_true", default=True)
    parser.add_argument("--ab-test", action="store_true", default=False, help="Run A/B champion vs rich pattern+timing candidate")
    parser.add_argument("--decision-every", type=int, default=8)
    args = parser.parse_args()

    import pandas as pd
    end = "2025-05-20"
    start = (pd.Timestamp(end) - pd.Timedelta(weeks=args.weeks)).strftime("%Y-%m-%d")

    cfg = BacktestConfig(
        symbol=args.symbol,
        start=start,
        end=end,
        decision_every_n_bars=args.decision_every,
        speed_mode=args.speed,
        use_patterns=args.use_patterns,
        use_news_events=True,
        verbose=True,
    )

    bt = FastBacktester(cfg)

    if getattr(args, "ab_test", False):
        from Python.backtest.fast_backtester import make_champion_policy, make_pattern_timing_candidate_policy
        ab = bt.run_ab_test(
            champion_policy=make_champion_policy(),
            new_policy=make_pattern_timing_candidate_policy(),
            champion_name="champion",
            new_name="pattern_timing_rich",
        )
        bt.save_results(filename=f"ab_validation_{args.symbol}_{args.weeks}w.json")
        print("\n=== FAST BACKTEST VALIDATION SUMMARY ===")
        print(f"Delta PnL: ${ab.get('delta',{}).get('pnl',0):+.2f}")
        print(f"Beats champion: {ab.get('candidate_beats_champion')}")
        print(f"Recommend promotion: {ab.get('recommend_for_promotion')}")
        print(f"Edge verdict: {ab.get('overall_edge')}")
    else:
        # Default: rich internal biased policy exercising pattern_context + timing_context -> dynamic TimeExitSpec
        results = bt.run()  # uses _default_biased_policy (rich pattern+timing)
        bt.save_results()

        print("\n=== Fast Backtest Summary ===")
        s = results.get("summary", {})
        print(f"Period: {s.get('period')}")
        print(f"Elapsed: {s.get('elapsed_seconds')}s")
        print(f"Final Equity: ${s.get('final_equity'):,.2f}")
        print(f"Trades: {s.get('total_trades')} | WR: {s.get('win_rate')}")
        print(f"TimeExit forced: {s.get('time_exit_forced')} (news={s.get('news_forced_closes')})")
        print("Pattern/timing scorecard:", s.get("pattern_timing_scorecard"))


if __name__ == "__main__":
    main()
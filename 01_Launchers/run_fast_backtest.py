#!/usr/bin/env python3
"""
Quick CLI for the new high-speed backtester.

Production zero-touch: easy 4-12 week campaigns feeding PromotionGates (pattern/timing/regime) + supervisor meta.

Examples:
    # 8-week campaign (recommended for canary)
    python scripts/run_fast_backtest.py --symbol XAUUSDm --weeks 8 --speed fast --campaign --apply-meta

    # Exact 42 days A/B with promotion artifacts
    python scripts/run_fast_backtest.py --symbol BTCUSDm --days 42 --ab-test --campaign
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from Python.backtest.fast_backtester import FastBacktester, BacktestConfig


def main():
    parser = argparse.ArgumentParser(description="Fast Backtester for Supreme Chainsaw - Production Long Validation Campaigns (4-12 weeks easy)")
    parser.add_argument("--symbol", default="XAUUSDm")
    parser.add_argument("--weeks", type=int, default=2, help="Weeks of data (use 4-12 for long validation campaigns)")
    parser.add_argument("--days", type=int, default=0, help="Alternative: exact days (overrides weeks if >0). Ideal for 28-84d campaigns")
    parser.add_argument("--speed", choices=["fast", "realistic"], default="fast")
    parser.add_argument("--use-patterns", action="store_true", default=True)
    parser.add_argument("--ab-test", action="store_true", default=False, help="Run A/B champion vs rich pattern+timing candidate (uses new gates)")
    parser.add_argument("--decision-every", type=int, default=8)
    parser.add_argument("--campaign", action="store_true", default=False, help="Campaign mode: write detailed results + edge scorecard to runtime/validation_results/ + backtest_results/ for promotion gates / supervisor consumption")
    parser.add_argument("--apply-meta", action="store_true", default=False, help="Load runtime/next_training_overrides.json and inject pattern/timing boosts into policy context")
    args = parser.parse_args()

    import pandas as pd
    from datetime import datetime
    from pathlib import Path
    import json

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    RUNTIME = PROJECT_ROOT / "runtime"
    VAL_DIR = RUNTIME / "validation_results"
    BT_RES_DIR = RUNTIME / "backtest_results"
    VAL_DIR.mkdir(parents=True, exist_ok=True)
    BT_RES_DIR.mkdir(parents=True, exist_ok=True)

    # Duration calc (supports easy 4-12 week campaigns)
    if args.days and args.days > 0:
        duration_str = f"{args.days}d"
        end = "2025-05-20"  # or current; adjust as needed for real data
        start = (pd.Timestamp(end) - pd.Timedelta(days=args.days)).strftime("%Y-%m-%d")
        weeks_eff = round(args.days / 7.0, 1)
    else:
        duration_str = f"{args.weeks}w"
        end = "2025-05-20"
        start = (pd.Timestamp(end) - pd.Timedelta(weeks=args.weeks)).strftime("%Y-%m-%d")
        weeks_eff = args.weeks

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

    # Meta overrides injection for campaign (pattern/timing boosts from supervisor/meta_optimizer)
    if args.apply_meta:
        meta_path = RUNTIME / "next_training_overrides.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                print(f"[CAMPAIGN] Applying meta overrides: patterns+{meta.get('feature_importance_overrides',{}).get('patterns',1)} timing+{meta.get('feature_importance_overrides',{}).get('timing',1)}")
                # Note: real policy injection would pass to FastBacktester; here we log for gate consumers
                cfg.__dict__.setdefault("meta_overrides", meta)
            except Exception as e:
                print(f"[CAMPAIGN] Meta load note: {e}")

    bt = FastBacktester(cfg)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_base = f"fast_campaign_{args.symbol}_{duration_str}_{ts}"

    if getattr(args, "ab_test", False):
        from Python.backtest.fast_backtester import make_champion_policy, make_pattern_timing_candidate_policy
        ab = bt.run_ab_test(
            champion_policy=make_champion_policy(),
            new_policy=make_pattern_timing_candidate_policy(),
            champion_name="champion",
            new_name="pattern_timing_rich",
        )
        fname = f"ab_validation_{args.symbol}_{duration_str}.json"
        bt.save_results(filename=fname)
        # Campaign output for promotion gates / supervisor / TUI
        if args.campaign:
            camp_path = VAL_DIR / f"{out_base}_ab.json"
            (BT_RES_DIR / fname).write_text(json.dumps(ab, default=str, indent=2)) if hasattr(BT_RES_DIR / fname, 'write_text') else None
            with open(camp_path, "w", encoding="utf-8") as f:
                json.dump({"ab": ab, "config": {"symbol":args.symbol, "duration":duration_str, "campaign":True}, "ts":ts, "recommend_promote": ab.get("recommend_for_promotion")}, f, indent=2, default=str)
            print(f"[CAMPAIGN] Wrote long-validation artifacts to {camp_path}")
        print("\n=== FAST BACKTEST VALIDATION SUMMARY (Long Campaign) ===")
        print(f"Delta PnL: ${ab.get('delta',{}).get('pnl',0):+.2f}")
        print(f"Beats champion: {ab.get('candidate_beats_champion')}")
        print(f"Recommend promotion: {ab.get('recommend_for_promotion')}")
        print(f"Edge verdict: {ab.get('overall_edge')}")
        print(f"Pattern/timing/regime edge (for new gates): see rich metrics in results")
    else:
        # Default: rich internal biased policy exercising pattern_context + timing_context -> dynamic TimeExitSpec
        results = bt.run()  # uses _default_biased_policy (rich pattern+timing)
        bt.save_results()

        print("\n=== Fast Backtest Summary (Long Validation Campaign) ===")
        s = results.get("summary", {})
        print(f"Period: {s.get('period')} (effective {duration_str})")
        print(f"Elapsed: {s.get('elapsed_seconds')}s")
        print(f"Final Equity: ${s.get('final_equity'):,.2f}")
        print(f"Trades: {s.get('total_trades')} | WR: {s.get('win_rate')}")
        print(f"TimeExit forced: {s.get('time_exit_forced')} (news={s.get('news_forced_closes')})")
        print("Pattern/timing scorecard:", s.get("pattern_timing_scorecard"))

        if args.campaign:
            camp_path = VAL_DIR / f"{out_base}.json"
            with open(camp_path, "w", encoding="utf-8") as f:
                json.dump({
                    "results": results,
                    "config": {"symbol": args.symbol, "weeks": weeks_eff, "days": args.days or None, "speed": args.speed, "campaign": True, "meta_applied": args.apply_meta},
                    "ts": ts,
                    "for_promotion_gates": {"pattern_timing_regime": s.get("pattern_timing_scorecard"), "recommend": (s.get("win_rate",0) > 0.48 and s.get("final_equity",0) > 0)}
                }, f, indent=2, default=str)
            print(f"[CAMPAIGN] Long 4-12w validation artifacts for supervisor/gates/TUI: {camp_path}")


if __name__ == "__main__":
    main()
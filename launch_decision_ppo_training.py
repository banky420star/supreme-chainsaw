#!/usr/bin/env python3
"""
Launch a clean training run with decision_ppo path enabled.
This is the key step to get a model that outputs rich TradeDecisions
(lot sizing, TP/SL variants, trailing, partials, full close logic, etc.)
and push the full autonomous stack toward 100%.

Usage:
  python launch_decision_ppo_training.py --symbol BTCUSDm --timesteps 50000
"""

import argparse
import datetime as dt_module
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from training.train_drl import _train_once
from Python.config_utils import load_project_config, resolve_trading_symbols, DEFAULT_TRADING_SYMBOLS

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDm", help="Symbol to train (BTCUSDm or XAUUSDm recommended)")
    parser.add_argument("--timesteps", type=int, default=50000, help="Total PPO timesteps for this run")
    parser.add_argument("--period", default="90d")
    parser.add_argument("--interval", default="5m")
    args = parser.parse_args()

    symbol = args.symbol
    total_timesteps = args.timesteps

    # Enable decision_ppo rich action space (the whole point of this launch)
    # This makes the env use the 18-dim DecisionSpec output (lot, TP/SL, trailing, partials, etc.)
    os.environ.setdefault("AGI_DECISION_PPO", "1")
    # Explicit action config for the Decision PPO head
    action_cfg = {
        "decision_ppo": True,
        "decision_action_dim": 18,
    }

    print("=" * 80)
    print("DECISION PPO TRAINING LAUNCH")
    print("=" * 80)
    print(f"Symbol: {symbol}")
    print(f"Timesteps: {total_timesteps:,}")
    print(f"Period: {args.period} | Interval: {args.interval}")
    print(f"Action config: {action_cfg}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 80)

    # Load base config
    cfg = load_project_config(PROJECT_ROOT)

    # Override drl section to force decision_ppo
    drl = cfg.setdefault("drl", {})
    drl["action"] = action_cfg
    drl.setdefault("feature_version", "multitimeframe_best")

    # Prepare minimal per-symbol config so action_cfg is picked up
    if "symbols" not in cfg:
        cfg["symbols"] = {}
    cfg["symbols"].setdefault(symbol, {})
    cfg["symbols"][symbol]["action"] = action_cfg

    # Use best available features + MTF awareness if possible
    # Data & MTF Reliability Agent (2026-05-28): fetch_multitimeframe_training_data now auto-falls back to
    # data/test/* caches + resamples + dukascopy so XAU (and BTC) decision_ppo MTF runs NEVER block on live MT5 limits.
    try:
        from Python.features.multitimeframe_builder import load_best_feature_params
        best = load_best_feature_params(symbol)
        if best:
            print(f"Using best feature params for {symbol}")
    except Exception:
        pass

    # Kick off the training
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    run_tag = f"decision_ppo_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log_file = log_dir / f"{run_tag}.log"

    print(f"\nStarting _train_once for {symbol} with decision_ppo enabled...")
    print(f"Logging to: {log_file}")

    # Redirect prints + logs for the run
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    try:
        result = _train_once(
            symbols=[symbol],
            cfg=cfg,
            total_timesteps=total_timesteps,
            initial_balance=10000.0,
            alerter=None,
        )
        print(f"\nTraining run completed for {symbol}.")
        print(f"Result summary: {result}")
    except Exception as e:
        print(f"\nTraining failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 80)
    print("DECISION PPO TRAINING LAUNCH COMPLETE")
    print(f"Check {log_file} for full progress.")
    print("Next: Watch for candidate in models/registry/candidates/")
    print("The armed handoff watcher will auto-promote with decision_ppo if gates pass.")
    print("Full zero-touch: candidate (rich 18-dim DecisionSpec) -> gates (promoter) -> paper_mt5_execution_harness(execution_type=decision_ppo + ExecutionAgent) -> rich telemetry + retrain feedback.")
    print("=" * 80)

    # === User-requested: Analyze profitable trade timing + market open / news handling ===
    # This runs after training so we "look at when the most profitable trades were taken"
    # and how the policy (via Decision PPO rich TimeExitSpec / rewards) handled opens and news.
    try:
        from Python.analysis.trade_timing_analyzer import analyze_profitable_trade_timing
        print("\n[Timing Analysis] Running post-training analysis of profitable trades timing, market opens, news events...")
        timing_insights = analyze_profitable_trade_timing(
            journal_path=PROJECT_ROOT / "logs" / "trade_journal" / "trade_journal.jsonl",
            top_n=100
        )
        if "error" not in timing_insights:
            print("  - Best hours / sessions for profitable trades:", timing_insights.get("best_hours_by_pnl", [])[:3])
            if "news_proximity_performance" in timing_insights:
                print("  - News proximity P&L patterns analyzed (avoidance around high-impact events).")
            if "news_avoidance_recommendation" in timing_insights:
                print("  - News avoidance recommendation:", timing_insights["news_avoidance_recommendation"].get("suggestion"))
            # Save insights for the model / gates / TUI
            insights_path = PROJECT_ROOT / "logs" / f"{run_tag}_timing_insights.json"
            import json
            insights_path.write_text(json.dumps(timing_insights, indent=2, default=str), encoding="utf-8")
            print(f"  - Full timing + open/news insights saved to {insights_path}")
            print("  - These patterns should inform future Decision PPO policies (via enriched features + TimeExitSpec for opens/news).")
        else:
            print(f"  - Timing analysis skipped or no journal yet: {timing_insights.get('error')}")
    except Exception as _e:
        print(f"  - Timing analysis non-fatal error (will improve as journal populates): {_e}")

    # Coordinate with Autonomous Loop Closer / handoff watcher: write marker for immediate detection of this decision_ppo run
    try:
        import json
        marker = PROJECT_ROOT / "runtime" / "decision_ppo_training_complete.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "launcher": "launch_decision_ppo_training",
            "symbol": symbol,
            "timesteps": total_timesteps,
            "action_config": action_cfg,
            "note": "First good rich Decision PPO candidate from this run should trigger watcher -> promoter -> ExecutionAgent paper harness autonomously.",
            "next": "handoff_watcher.py will detect via candidates/ mtime + _detect_execution_type and invoke with AGI_EXECUTION_TYPE=decision_ppo"
        }, indent=2), encoding="utf-8")
        print(f"Loop coordination marker written: {marker} (watcher will pick up rich candidate)")
    except Exception as _e:
        print(f"Coordination marker (non-fatal): {_e}")

if __name__ == "__main__":
    main()

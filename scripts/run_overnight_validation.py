#!/usr/bin/env python3
"""
Overnight Validation Campaign Launcher.

Runs 3-month realistic A/B backtests on XAU/BTC using the FastBacktester + ValidationHarness
in < 30 minutes wall time (fast mode).

Usage (PowerShell / CMD):
    .\.venv312\Scripts\python.exe scripts\run_overnight_validation.py
    .\.venv312\Scripts\python.exe scripts\run_overnight_validation.py --symbols XAUUSDm --months 3

Results feed directly into:
- Retraining orchestrator (standardized JSON artifacts)
- TUI / mini watcher (via agent_status + reports)
- Autonomous self-evolution loop
"""

import argparse
import sys
from pathlib import Path

# Bootstrap
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from Python.autonomous.validation_harness import ValidationHarness, CampaignConfig, run_overnight_xau_btc_3m


def main():
    parser = argparse.ArgumentParser(description="Launch overnight-style long validation campaigns")
    parser.add_argument("--symbols", default="XAUUSDm,BTCUSDm", help="Comma separated symbols")
    parser.add_argument("--months", type=int, default=3, help="Approximate months of data per symbol")
    parser.add_argument("--speed", default="fast", choices=["fast", "realistic"])
    parser.add_argument("--campaign-name", default="overnight")
    args = parser.parse_args()

    print("=" * 70)
    print("SUPREME CHAINSAW — OVERNIGHT VALIDATION CAMPAIGN")
    print("=" * 70)
    print(f"Symbols : {args.symbols}")
    print(f"Duration: ~{args.months} months per symbol (fast engine)")
    print(f"Speed   : {args.speed}")
    print("Target  : <30min total for 3mo XAU+BTC A/B with pattern+timing+TimeExitSpec")
    print("=" * 70)

    weeks = int(args.months * 4.3)

    harness = ValidationHarness(campaign_name=f"{args.campaign_name}_{args.months}m")
    cfg = CampaignConfig(
        name=f"overnight_{args.campaign_name}_{args.months}m",
        symbols=[s.strip() for s in args.symbols.split(",") if s.strip()],
        durations_weeks=[weeks],
        speed=args.speed,
    )

    results = harness.run_campaign(cfg)

    print("\n" + "=" * 70)
    print("CAMPAIGN COMPLETE — STANDARDIZED RESULTS READY FOR RETRAINING")
    print("=" * 70)
    if isinstance(results, (list, tuple)):
        for r in results:
            if hasattr(r, 'overall_recommendation'):
                verdict = r.overall_recommendation
                beats = getattr(r, 'ab_comparison', {}).get("candidate_beats_champion") if hasattr(r, 'ab_comparison') else None
                period = getattr(r, 'period', 'N/A')
                sym = getattr(r, 'symbols', ['?'])[0] if hasattr(r, 'symbols') else '?'
                print(f"  {sym} {period}: {verdict} | beats_champion={beats}")
                rp = getattr(r, 'rich_report_path', 'N/A')
                print(f"    → Report: {rp}")
            else:
                print(f"  Result: {r}")
    else:
        print(f"  Result object: {results}")

    print(f"\nAgent status: runtime/agent_status/validation_harness_agent.json")
    print(f"Artifacts:    runtime/validation_results/ + reports/validation/")
    print("These feed the autonomous retraining loop directly.\n")


if __name__ == "__main__":
    import pandas as pd  # for any timestamp math inside harness
    main()

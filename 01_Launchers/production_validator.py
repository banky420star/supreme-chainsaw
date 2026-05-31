"""
Production Readiness Validator

Checks if the system is ready for live trading based on:
1. Training completion
2. Backtest results
3. Paper trading performance
4. Risk management settings

Usage:
    python scripts/production_validator.py --phase 1|2|3
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def check_training_completion():
    """Check if enhanced training has completed successfully."""
    logs_dir = PROJECT_ROOT / "logs"
    # Only get main training results (not per-symbol files)
    training_files = [f for f in logs_dir.glob("enhanced_training_results_*.json")
                      if "_BTCUSDm_" not in f.name
                      and "_XAUUSDm_" not in f.name
                      and "_EURUSDm_" not in f.name
                      and "_GBPUSDm_" not in f.name]

    if not training_files:
        return False, "No training results found. Run: python start_enhanced_training.py"

    # Get most recent
    latest = max(training_files, key=os.path.getmtime)
    try:
        with open(latest) as f:
            results = json.load(f)

        symbols_trained = results.get("symbols", [])
        per_symbol = results.get("per_symbol_metrics", {})

        if len(symbols_trained) == 0:
            return False, "No symbols trained"

        # Check timeframe selections
        tf_selections = results.get("timeframe_selections", {})
        for symbol in symbols_trained:
            if symbol not in tf_selections:
                return False, f"No timeframe selection for {symbol}"

        return True, f"Training complete for {len(symbols_trained)} symbols"
    except Exception as e:
        return False, f"Error reading training results: {e}"


def check_backtest_results():
    """Validate backtest results meet production criteria."""
    logs_dir = PROJECT_ROOT / "logs"
    backtest_files = list(logs_dir.glob("backtest_production.json"))

    if not backtest_files:
        return False, "No backtest results found. Run backtester.py first"

    try:
        with open(backtest_files[0]) as f:
            results = json.load(f)

        checks = []

        # Sharpe ratio
        sharpe = results.get("sharpe_ratio", 0)
        if sharpe < 1.0:
            checks.append(f"[FAIL] Sharpe ratio {sharpe:.2f} < 1.0")
        else:
            checks.append(f"[OK] Sharpe ratio {sharpe:.2f}")

        # Max drawdown
        dd = results.get("max_drawdown_pct", 100)
        if dd > 15:
            checks.append(f"[FAIL] Max drawdown {dd:.1f}% > 15%")
        else:
            checks.append(f"[OK] Max drawdown {dd:.1f}%")

        # Win rate
        wr = results.get("win_rate", 0)
        if wr < 50:
            checks.append(f"[FAIL] Win rate {wr:.1f}% < 50%")
        else:
            checks.append(f"[OK] Win rate {wr:.1f}%")

        # Profit factor
        pf = results.get("profit_factor", 0)
        if pf < 1.2:
            checks.append(f"[FAIL] Profit factor {pf:.2f} < 1.2")
        else:
            checks.append(f"[OK] Profit factor {pf:.2f}")

        # Sample size
        trades = results.get("total_trades", 0)
        if trades < 100:
            checks.append(f"[WARN] Only {trades} trades (< 100)")
        else:
            checks.append(f"[OK] {trades} trades")

        passed = sharpe >= 1.0 and dd <= 15 and wr >= 50 and pf >= 1.2

        return passed, "\n   ".join([""] + checks)
    except Exception as e:
        return False, f"Error reading backtest: {e}"


def check_paper_trading():
    """Check paper trading performance."""
    logs_dir = PROJECT_ROOT / "logs"

    # Look for trade events
    trade_files = list(logs_dir.glob("trade_events_*.jsonl"))
    if not trade_files:
        return False, "No trade events found. Start paper trading first"

    # Get recent files (last 7 days)
    recent_files = []
    cutoff = datetime.now() - timedelta(days=7)
    for f in trade_files:
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        if mtime > cutoff:
            recent_files.append(f)

    if not recent_files:
        return False, "No recent paper trading activity (last 7 days)"

    # Analyze trades
    total_pnl = 0
    wins = 0
    losses = 0

    for f in recent_files:
        try:
            with open(f) as file:
                for line in file:
                    event = json.loads(line)
                    if event.get("event") == "trade_closed":
                        pnl = event["payload"].get("profit", 0)
                        total_pnl += pnl
                        if pnl > 0:
                            wins += 1
                        else:
                            losses += 1
        except:
            continue

    total = wins + losses
    if total == 0:
        return False, "No completed trades found"

    win_rate = (wins / total) * 100
    profit_factor = abs(wins * total_pnl / total) / abs(losses * total_pnl / total) if losses > 0 and total_pnl != 0 else float('inf')

    checks = []
    checks.append(f"Trades: {total} ({wins}W/{losses}L)")
    checks.append(f"P&L: ${total_pnl:.2f}")
    checks.append(f"Win Rate: {win_rate:.1f}%")

    passed = win_rate >= 50 and total >= 20 and total_pnl > 0

    if total < 20:
        checks.append(f"[WARN] Only {total} trades (< 20)")
    if win_rate < 50:
        checks.append(f"[FAIL] Win rate {win_rate:.1f}% < 50%")
    if total_pnl <= 0:
        checks.append(f"[FAIL] Not profitable (${total_pnl:.2f})")

    return passed, "\n   ".join([""] + checks)


def check_risk_settings(phase):
    """Verify risk settings appropriate for phase."""
    risk_percent = float(os.environ.get("AGI_RISK_PERCENT", 2.0))
    max_pos = int(os.environ.get("AGI_MAX_POS_PER_SYMBOL", 3))

    if phase == 3:  # Micro live
        if risk_percent > 1.0:
            return False, f"[FAIL] Risk {risk_percent}% too high for Phase 3 (max 1%)"
        if max_pos > 2:
            return False, f"[FAIL] Max positions {max_pos} too high (max 2)"
        return True, f"[OK] Conservative risk: {risk_percent}% per trade, max {max_pos} positions"

    elif phase == 4:  # Production
        if risk_percent > 2.0:
            return False, f"[FAIL] Risk {risk_percent}% > max 2%"
        return True, f"[OK] Risk settings: {risk_percent}% per trade"

    return True, "[OK] Risk settings OK"


def check_account_size():
    """Check account has sufficient capital."""
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            return False, "[FAIL] MT5 not initialized"

        account = mt5.account_info()
        if account is None:
            return False, "[FAIL] Could not get account info"

        balance = account.balance

        if balance < 1000:
            return False, f"[FAIL] Account balance ${balance:.2f} < $1,000 minimum"
        elif balance < 5000:
            return True, f"[WARN] Account balance ${balance:.2f} (recommended $5,000+)"
        else:
            return True, f"[OK] Account balance ${balance:.2f}"
    except Exception as e:
        return False, f"[FAIL] MT5 error: {e}"


def main():
    parser = argparse.ArgumentParser(description="Validate production readiness")
    parser.add_argument("--phase", type=int, default=1, help="Phase to validate (1-4)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"PRODUCTION VALIDATOR - Phase {args.phase}")
    print("=" * 60)
    print()

    all_passed = True

    # Phase 1: Training & Backtest
    if args.phase >= 1:
        print("Phase 1: Training & Backtest")
        print("-" * 40)

        passed, msg = check_training_completion()
        print(f"Training: {msg}")
        if not passed:
            all_passed = False

        passed, msg = check_backtest_results()
        print(f"Backtest: {msg}")
        if not passed:
            all_passed = False

        print()

    # Phase 2: Paper Trading
    if args.phase >= 2:
        print("Phase 2: Paper Trading")
        print("-" * 40)

        passed, msg = check_paper_trading()
        print(f"Paper Trading: {msg}")
        if not passed:
            all_passed = False

        print()

    # Phase 3-4: Live Trading
    if args.phase >= 3:
        print("Phase 3-4: Live Trading Setup")
        print("-" * 40)

        passed, msg = check_account_size()
        print(f"Account: {msg}")
        if not passed:
            all_passed = False

        passed, msg = check_risk_settings(args.phase)
        print(f"Risk Settings: {msg}")
        if not passed:
            all_passed = False

        print()

    # Final verdict
    print("=" * 60)
    if all_passed:
        print("ALL CHECKS PASSED")
        print(f"Ready for Phase {args.phase}")
        if args.phase < 4:
            print(f"\nNext step: Run validator with --phase {args.phase + 1}")
        else:
            print("\nProduction ready!")
        return 0
    else:
        print("SOME CHECKS FAILED")
        print("Fix issues above before proceeding")
        return 1


if __name__ == "__main__":
    sys.exit(main())

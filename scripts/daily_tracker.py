"""
Daily Performance Tracker

Tracks and reports daily trading performance.
Run this at end of trading day.

Usage:
    python scripts/daily_tracker.py
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_today_trades():
    """Load all trades from today."""
    logs_dir = PROJECT_ROOT / "logs"
    today = datetime.now().strftime("%Y%m%d")

    trades = []

    # Look in trade_events files
    for log_file in logs_dir.glob("trade_events_*.jsonl"):
        try:
            with open(log_file) as f:
                for line in f:
                    event = json.loads(line)
                    if event.get("event") == "trade_closed":
                        # Check if trade is from today
                        ts = event.get("ts", "")
                        if today in ts.replace("-", "").replace("T", ""):
                            trades.append(event["payload"])
        except:
            continue

    return trades


def calculate_metrics(trades):
    """Calculate performance metrics."""
    if not trades:
        return None

    total_pnl = sum(t.get("profit", 0) for t in trades)
    wins = sum(1 for t in trades if t.get("profit", 0) > 0)
    losses = len(trades) - wins

    win_pnl = sum(t.get("profit", 0) for t in trades if t.get("profit", 0) > 0)
    loss_pnl = abs(sum(t.get("profit", 0) for t in trades if t.get("profit", 0) < 0))

    avg_win = win_pnl / wins if wins > 0 else 0
    avg_loss = loss_pnl / losses if losses > 0 else 0

    return {
        "total_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / len(trades)) * 100 if trades else 0,
        "total_pnl": total_pnl,
        "profit_factor": win_pnl / loss_pnl if loss_pnl > 0 else float('inf'),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def check_alerts(metrics):
    """Check for risk management alerts."""
    alerts = []

    if metrics["win_rate"] < 40:
        alerts.append(f"⚠️ Low win rate: {metrics['win_rate']:.1f}%")

    if metrics["total_pnl"] < -100:
        alerts.append(f"🚨 Significant loss: ${metrics['total_pnl']:.2f}")

    if metrics["losses"] >= 5 and metrics["wins"] == 0:
        alerts.append("🛑 STOP TRADING: 5 consecutive losses")

    if metrics["profit_factor"] < 0.8:
        alerts.append(f"⚠️ Poor profit factor: {metrics['profit_factor']:.2f}")

    return alerts


def main():
    print("=" * 60)
    print(f"DAILY PERFORMANCE REPORT - {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 60)
    print()

    # Load trades
    trades = load_today_trades()

    if not trades:
        print("No trades recorded today.")
        print()
        print("If you expected trades, check:")
        print("  1. Is the server running?")
        print("  2. Is trading enabled?")
        print("  3. Check logs/trade_events_*.jsonl")
        return 0

    # Calculate metrics
    metrics = calculate_metrics(trades)

    print(f"📊 Trading Activity")
    print("-" * 40)
    print(f"Total Trades: {metrics['total_trades']}")
    print(f"  Wins: {metrics['wins']} ({metrics['win_rate']:.1f}%)")
    print(f"  Losses: {metrics['losses']}")
    print()

    print(f"💰 P&L Summary")
    print("-" * 40)
    pnl_color = "🟢" if metrics['total_pnl'] >= 0 else "🔴"
    print(f"Total P&L: {pnl_color} ${metrics['total_pnl']:.2f}")
    print(f"Avg Win: ${metrics['avg_win']:.2f}")
    print(f"Avg Loss: ${metrics['avg_loss']:.2f}")
    print(f"Profit Factor: {metrics['profit_factor']:.2f}")
    print()

    # Check alerts
    alerts = check_alerts(metrics)
    if alerts:
        print("⚠️  ALERTS")
        print("-" * 40)
        for alert in alerts:
            print(f"  {alert}")
        print()

    # Weekly summary (if today is Sunday)
    if datetime.now().weekday() == 6:  # Sunday
        print("📈 Weekly Review Due")
        print("-" * 40)
        print("Run: python scripts/weekly_review.py")
        print()

    # Save daily summary
    summary_file = PROJECT_ROOT / "logs" / "daily_summaries.jsonl"
    with open(summary_file, "a") as f:
        record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "metrics": metrics,
            "alerts": alerts,
        }
        f.write(json.dumps(record) + "\n")

    print(f"✅ Report saved to logs/daily_summaries.jsonl")
    print()

    return 0 if not alerts else 1


if __name__ == "__main__":
    sys.exit(main())

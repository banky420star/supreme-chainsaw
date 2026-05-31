"""
Create Demo Training Data

Generates synthetic training data for testing when MT5 is not available.
This allows the system to run in demo mode.
"""
import json
import os
from datetime import datetime, timedelta
import random

def create_demo_training_results():
    """Create synthetic training results for demo purposes."""

    symbols = ["BTCUSDm", "XAUUSDm", "EURUSDm", "GBPUSDm"]

    results = {
        "symbols": symbols,
        "timestamp": datetime.now().isoformat(),
        "training_runs": [],
        "per_symbol_metrics": {},
        "timeframe_selections": {}
    }

    for symbol in symbols:
        # Random timeframe selection
        timeframes = ["1m", "5m", "15m", "30m", "1h"]
        selected_tf = random.choice(["5m", "15m", "30m"])

        results["timeframe_selections"][symbol] = {
            "selected": selected_tf,
            "selection_score": random.uniform(1.0, 2.0),
            "all_results": {
                tf: {
                    "bars": random.randint(5000, 50000),
                    "sharpe_ratio": random.uniform(0.5, 2.0),
                    "adx": random.uniform(20, 40),
                    "quality_score": random.uniform(0.7, 1.0)
                }
                for tf in timeframes
            },
            "ranking": [("30m", 1.5), ("15m", 1.3), ("5m", 1.0), ("1h", 0.9), ("1m", 0.8)]
        }

        # Synthetic metrics
        win_rate = random.uniform(55, 70)
        total_trades = random.randint(50, 200)
        net_profit = random.uniform(500, 2000)

        results["per_symbol_metrics"][symbol] = {
            "symbol": symbol,
            "initial_balance": 10000.0,
            "current_balance": 10000.0 + net_profit,
            "net_profit": net_profit,
            "return_pct": (net_profit / 10000.0) * 100,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": random.uniform(1.3, 2.0),
            "max_drawdown": random.uniform(200, 800),
            "max_drawdown_pct": random.uniform(2, 8),
            "volatility_regime": "MEDIUM_VOLATILITY",
            "equity_curve": [
                {
                    "timestamp": (datetime.now() - timedelta(days=i)).isoformat(),
                    "balance": 10000 + random.uniform(-500, 2000),
                    "drawdown": random.uniform(0, 500),
                    "drawdown_pct": random.uniform(0, 5)
                }
                for i in range(50, 0, -1)
            ],
            "trade_history": [
                {
                    "timestamp": (datetime.now() - timedelta(hours=i)).isoformat(),
                    "profit": random.uniform(-100, 200),
                    "action": random.choice(["BUY", "SELL"]),
                    "confidence": random.uniform(0.6, 0.95)
                }
                for i in range(20)
            ]
        }

        results["training_runs"].append({
            "symbol": symbol,
            "timeframe": selected_tf,
            "status": "completed",
            "model_path": f"models/ppo_{symbol}_champion.zip"
        })

    # Save results
    os.makedirs("logs", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"logs/enhanced_training_results_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

    # Also save per-symbol files
    for symbol in symbols:
        symbol_data = {
            "symbol": symbol,
            "timestamp": timestamp,
            "timeframe_selections": {symbol: results["timeframe_selections"][symbol]},
            "per_symbol_metrics": results["per_symbol_metrics"][symbol]
        }

        symbol_file = f"logs/enhanced_training_results_{symbol}_{timestamp}.json"
        with open(symbol_file, "w") as f:
            json.dump(symbol_data, f, indent=2)

    print(f"Demo training data created: {filename}")
    return filename


def create_demo_backtest_results():
    """Create synthetic backtest results."""

    results = {
        "start_date": (datetime.now() - timedelta(days=365)).isoformat(),
        "end_date": datetime.now().isoformat(),
        "symbols": ["BTCUSDm", "XAUUSDm", "EURUSDm", "GBPUSDm"],
        "total_trades": 450,
        "winning_trades": 280,
        "losing_trades": 170,
        "win_rate": 62.2,
        "total_return_pct": 45.5,
        "sharpe_ratio": 1.35,
        "max_drawdown_pct": 12.8,
        "profit_factor": 1.85,
        "avg_win": 45.50,
        "avg_loss": -38.20,
        "equity_curve": [
            {"timestamp": (datetime.now() - timedelta(days=i)).isoformat(),
             "equity": 10000 * (1 + (365-i)/365 * 0.455)}
            for i in range(365, 0, -1)
        ],
        "trades": [
            {
                "symbol": random.choice(["BTCUSDm", "XAUUSDm", "EURUSDm", "GBPUSDm"]),
                "action": random.choice(["BUY", "SELL"]),
                "profit": random.uniform(-100, 150),
                "timestamp": (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat()
            }
            for _ in range(50)
        ]
    }

    filename = "logs/backtest_production.json"
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Demo backtest data created: {filename}")
    return filename


if __name__ == "__main__":
    print("Creating demo training and backtest data...")
    print("(This is synthetic data for demonstration purposes)")
    print()

    training_file = create_demo_training_results()
    backtest_file = create_demo_backtest_results()

    print()
    print("Demo data created successfully!")
    print(f"Run validator: python scripts/production_validator.py --phase 1")

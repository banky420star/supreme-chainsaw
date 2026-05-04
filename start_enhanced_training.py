"""Launch enhanced training with per-symbol metrics and multi-timeframe optimization."""
import argparse
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from Python.config_utils import DEFAULT_TRADING_SYMBOLS, load_project_config, resolve_trading_symbols
from training.enhanced_train_drl import EnhancedTrainingPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced DRL Training with Per-Symbol Metrics and Multi-Timeframe Optimization"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols (e.g., BTCUSDm,EURUSDm). If not provided, uses config."
    )
    parser.add_argument(
        "--timeframe-opt",
        action="store_true",
        default=True,
        help="Enable multi-timeframe optimization (tests M1, M5, M15, M30, H1 and picks best)"
    )
    parser.add_argument(
        "--no-timeframe-opt",
        action="store_true",
        help="Disable timeframe optimization"
    )
    parser.add_argument(
        "--per-symbol-metrics",
        action="store_true",
        default=True,
        help="Enable per-symbol profit, balance, and drawdown tracking"
    )
    parser.add_argument(
        "--no-per-symbol-metrics",
        action="store_true",
        help="Disable per-symbol metrics"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run in live mode with MT5 connection"
    )

    args = parser.parse_args()

    # Handle negated flags
    enable_timeframe_opt = not args.no_timeframe_opt if args.no_timeframe_opt else args.timeframe_opt
    enable_per_symbol_metrics = not args.no_per_symbol_metrics if args.no_per_symbol_metrics else args.per_symbol_metrics

    # Parse symbols
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        # Load from config
        cfg = load_project_config(PROJECT_ROOT, live_mode=args.live)
        symbols = resolve_trading_symbols(cfg, fallback=DEFAULT_TRADING_SYMBOLS)

    print("=" * 80)
    print("ENHANCED DRL TRAINING LAUNCHER")
    print("=" * 80)
    print(f"Symbols: {symbols}")
    print(f"Timeframe optimization: {enable_timeframe_opt}")
    print(f"Per-symbol metrics: {enable_per_symbol_metrics}")
    print(f"Live mode: {args.live}")
    print("=" * 80)
    print()

    # Run pipeline
    pipeline = EnhancedTrainingPipeline(config_path=args.config)
    results = pipeline.run_training_with_timeframe_optimization(
        symbols=symbols,
        enable_timeframe_opt=enable_timeframe_opt,
        enable_per_symbol_metrics=enable_per_symbol_metrics,
    )

    # Print summary
    print("\n" + "=" * 80)
    print("TRAINING COMPLETE")
    print("=" * 80)

    for run in results.get("training_runs", []):
        symbol = run.get("symbol")
        status = run.get("status", "unknown")
        tf = run.get("timeframe", "N/A")
        print(f"\n{symbol}:")
        print(f"  Status: {status.upper()}")
        print(f"  Timeframe: {tf}")

        metrics = results.get("per_symbol_metrics", {}).get(symbol, {})
        if metrics:
            print(f"  Net Profit: ${metrics.get('net_profit', 0):.2f}")
            print(f"  Return: {metrics.get('return_pct', 0):.2f}%")
            print(f"  Max Drawdown: {metrics.get('max_drawdown_pct', 0):.2f}%")
            print(f"  Total Trades: {metrics.get('total_trades', 0)}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()

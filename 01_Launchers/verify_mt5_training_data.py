"""
MT5 Training Data Verification Script for Chain Gambler (First Real Run Prep)

Tests the exact data ingestion path used by enhanced DRL / train_drl training:
- Uses Python.data_feed.fetch_training_data (source=mt5 preferred)
- Respects MT5_* env vars + config.yaml mt5 section (ENV: refs)
- Verifies BTCUSDm and XAUUSDm (primary targets)
- Reports bar counts, date ranges, NaN handling, and basic feature readiness

Usage (once MT5 terminal is running + logged in with trial creds):
    # Recommended: set env (PowerShell)
    $env:MT5_LOGIN = "435656990"
    $env:MT5_PASSWORD = "Fuckyou2/"
    $env:MT5_SERVER = "Exness-MT5Trial9"
    $env:AGI_MT5_MAX_BARS = "200000"

    cd C:\supreme-chainsaw
    python scripts\verify_mt5_training_data.py

    # Or with venv explicit
    .\.venv312\Scripts\python.exe scripts\verify_mt5_training_data.py --symbols BTCUSDm,XAUUSDm --bars 5000

Exits 0 on success (minimum viable data), 1 on hard failure.
Also safe to run with source=dukascopy for pre-MT5 smoke (no terminal needed).
"""

import argparse
import os
import sys
from datetime import datetime

# Ensure project root on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from Python.data_feed import fetch_training_data, _initialize_mt5
from Python.config_utils import load_project_config, resolve_trading_symbols, DEFAULT_TRADING_SYMBOLS


def main():
    parser = argparse.ArgumentParser(description="Verify real MT5 (or dukascopy) candle data for DRL training")
    parser.add_argument("--symbols", type=str, default="BTCUSDm,XAUUSDm",
                        help="Comma-separated symbols (default: BTCUSDm,XAUUSDm)")
    parser.add_argument("--bars", type=int, default=5000,
                        help="Minimum bars to request per symbol (default 5000 ~ few weeks M5)")
    parser.add_argument("--interval", type=str, default="5m", help="Timeframe (default 5m)")
    parser.add_argument("--period", type=str, default="30d", help="Period string (default 30d)")
    parser.add_argument("--source", type=str, default="mt5", choices=["mt5", "dukascopy", "auto"],
                        help="Data source (default mt5; use dukascopy for no-terminal test)")
    parser.add_argument("--strict", action="store_true", help="Fail hard on insufficient data")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print("=" * 80)
    print("CHAIN GAMBLER - MT5 TRAINING DATA VERIFIER")
    print("=" * 80)
    print(f"Symbols: {symbols}")
    print(f"Target bars: {args.bars} | interval: {args.interval} | period: {args.period}")
    print(f"Source: {args.source}")
    print(f"MT5_LOGIN set: {bool(os.environ.get('MT5_LOGIN'))}")
    print(f"MT5_SERVER set: {bool(os.environ.get('MT5_SERVER'))}")
    print()

    # Quick MT5 init probe (non-fatal)
    try:
        ok = _initialize_mt5()
        print(f"MT5 initialize probe: {'SUCCESS' if ok else 'NO CONNECTION (will try per-fetch)'}")
    except Exception as e:
        print(f"MT5 probe warning: {e}")

    print()

    success_count = 0
    min_viable = max(1000, args.bars // 5)  # generous for first run

    for sym in symbols:
        print(f"--- Fetching {sym} ---")
        try:
            df = fetch_training_data(
                sym,
                period=args.period,
                interval=args.interval,
                bars=args.bars,
                min_bars=min_viable,
                source=args.source,
                strict=args.strict,
            )
            n = len(df)
            if n == 0:
                print(f"  EMPTY DATA for {sym}")
                continue

            start = df.index.min() if hasattr(df, 'index') else 'N/A'
            end = df.index.max() if hasattr(df, 'index') else 'N/A'
            cols = list(df.columns) if hasattr(df, 'columns') else []
            has_ohlc = all(c in cols for c in ['open', 'high', 'low', 'close'])

            print(f"  OK: {n} bars | range: {start} -> {end}")
            print(f"  Columns: {cols[:8]}{'...' if len(cols) > 8 else ''}")
            print(f"  Has OHLC: {has_ohlc}")

            # Basic NaN / volume check
            nan_pct = df.isna().mean().mean() * 100 if hasattr(df, 'isna') else 0
            vol_col = 'volume' if 'volume' in cols else ('tick_volume' if 'tick_volume' in cols else None)
            print(f"  NaN% (overall): {nan_pct:.2f}%")
            if vol_col:
                vol_stats = df[vol_col].describe()
                print(f"  {vol_col} stats: mean={vol_stats['mean']:.1f} min={vol_stats['min']:.0f} max={vol_stats['max']:.0f}")

            if n >= min_viable:
                success_count += 1
                print(f"  STATUS: VIABLE for training (>= {min_viable} bars)")
            else:
                print(f"  STATUS: PARTIAL (recommend loading more history in MT5 charts)")

        except Exception as exc:
            print(f"  FAILED: {exc}")
            if args.strict:
                sys.exit(1)

        print()

    print("=" * 80)
    print(f"SUMMARY: {success_count}/{len(symbols)} symbols have viable training data")
    if success_count == len(symbols):
        print("READY FOR FIRST REAL MT5 DRL TRAINING CYCLE.")
        print("Next: python start_enhanced_training.py --symbols BTCUSDm,XAUUSDm --no-timeframe-opt ...")
        sys.exit(0)
    else:
        print("Some symbols short on data. In MT5 terminal: open charts + scroll back for BTCUSDm/XAUUSDm on M1/M5.")
        print("Re-run this verifier after history load.")
        sys.exit(1 if success_count == 0 else 0)


if __name__ == "__main__":
    main()

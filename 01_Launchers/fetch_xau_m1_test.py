"""Robust test fetcher for 10k M1 bars of XAUUSDm."""
import os
import sys
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import numpy as np
from Python.mt5_compat import mt5, MT5_AVAILABLE

def fetch_xau_m1_bars(count: int = 10000) -> list[dict]:
    """Fetch last N 1-minute bars for XAUUSDm."""
    if not MT5_AVAILABLE:
        print("MT5 package not available")
        return []

    if not mt5.initialize():
        print("Failed to initialize MT5")
        return []

    try:
        rates = mt5.copy_rates_from_pos("XAUUSDm", mt5.TIMEFRAME_M1, 0, count)
    finally:
        mt5.shutdown()

    if rates is None or len(rates) == 0:
        print("No rates returned from MT5")
        return []

    candles = []
    for r in rates:
        # numpy structured array row
        ts = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)

        # Safely get fields (works for both numpy.void and dict)
        def get_field(name, default=0.0):
            try:
                return float(r[name])
            except (KeyError, ValueError, TypeError):
                return default

        candle = {
            "symbol": "XAUUSDm",
            "timeframe": "1m",
            "timestamp": ts.isoformat(),
            "open": get_field("open"),
            "high": get_field("high"),
            "low": get_field("low"),
            "close": get_field("close"),
            "volume": get_field("tick_volume") or get_field("volume"),
            "spread": get_field("spread"),
        }
        candles.append(candle)

    return candles

def main():
    print("Fetching 10,000 1-minute bars of XAUUSDm ...")
    candles = fetch_xau_m1_bars(10_000)

    if not candles:
        print("Failed to fetch candles.")
        return

    # Save to clean test location
    os.makedirs("data/test", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"data/test/xauusd_m1_10k_{timestamp}.jsonl"

    import json
    with open(out_path, "w", encoding="utf-8") as f:
        for c in candles:
            f.write(json.dumps(c) + "\n")

    print(f"\n✓ Successfully fetched {len(candles):,} bars")
    print(f"  First bar: {candles[0]['timestamp']}")
    print(f"  Last bar : {candles[-1]['timestamp']}")
    print(f"  Saved to : {out_path}")

    # Quick stats
    closes = [c["close"] for c in candles]
    print(f"\nQuick stats:")
    print(f"  Min close: {min(closes):.2f}")
    print(f"  Max close: {max(closes):.2f}")
    print(f"  First close: {closes[0]:.2f}")
    print(f"  Last close : {closes[-1]:.2f}")

if __name__ == "__main__":
    main()

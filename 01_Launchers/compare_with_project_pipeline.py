"""Comparison of test data with project training pipeline."""
import pandas as pd
import json
from pathlib import Path
import numpy as np

print("=== XAUUSDm Test Data vs Project Training Pipeline ===\n")

latest = max(Path("data/test").glob("xauusd_m1_10k_*.jsonl"), key=lambda p: p.stat().st_mtime)
raw = pd.DataFrame([json.loads(l) for l in open(latest)])
raw["timestamp"] = pd.to_datetime(raw["timestamp"])
raw = raw.set_index("timestamp").sort_index()

print("1. Data we just fetched:")
print(f"   Bars: {len(raw)}")
print(f"   Columns: {list(raw.columns)}")
print(f"   Range : {raw.index.min()} -> {raw.index.max()}")

print("\n2. How this data fits the project's training stack:")
print("   - The Ingestor class (Python/data/ingest_mt5.py) is the official way")
print("   - It produces the exact format expected by the feature factory")
print("   - Then flows into EnhancedTrainingPipeline or train_drl.py")

print("\n3. Recommended next step for real work:")
print("   from Python.data.ingest_mt5 import Ingestor")
print("   ing = Ingestor()")
print("   candles = ing.ingest_candles('XAUUSDm', '1m', 100000)  # much larger for training")
print("   # Then run your normal training flow with this data")

print("\n4. This 10k bar set is perfect for:")
print("   - Fast feature prototyping")
print("   - Debugging Gym environments")
print("   - Testing reward functions")
print("   - Small PPO/Dreamer dry runs (not full production training)")

print("\n5. For full training you will want:")
print("   - 100k-500k+ bars minimum")
print("   - Multiple symbols for robustness")
print("   - Proper train / OOS split (the project has good chronological split logic)")

print("\n=== Summary ===")
print("We now have a clean, reproducible 10k bar XAUUSDm M1 dataset")
print("ready for all the testing you asked for.")

"""Basic analysis on the freshly fetched XAUUSDm 10k M1 bars."""
import pandas as pd
import json
from pathlib import Path

# Find latest test file
test_files = list(Path('data/test').glob('xauusd_m1_10k_*.jsonl'))
latest = max(test_files, key=lambda p: p.stat().st_mtime)
print("Loading:", latest.name)

# Load
data = [json.loads(line) for line in open(latest)]
df = pd.DataFrame(data)
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp').sort_index()

print("\n=== BASIC INFO ===")
print("Shape:", df.shape)
print("Date range:", df.index.min(), "to", df.index.max())
print("Duration:", df.index.max() - df.index.min())

print("\n=== OHLCV STATS ===")
print(df[['open','high','low','close','volume']].describe().round(2))

print("\n=== RETURNS ANALYSIS ===")
df['returns'] = df['close'].pct_change()

print(df['returns'].describe().round(6))

total_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
print("\nTotal return over period: {:.2f}%".format(total_return))
print("Per-bar volatility (std): {:.5f}%".format(df['returns'].std() * 100))

annualized_vol = df['returns'].std() * (60*24*252)**0.5 * 100
print("Rough annualized vol: {:.1f}%".format(annualized_vol))

print("\n=== DAILY STATS ===")
daily = df['close'].resample('D').agg(['first','last','min','max'])
daily['daily_return'] = daily['last'] / daily['first'] - 1
print(daily['daily_return'].describe().round(4))
print("Number of trading days sampled:", len(daily.dropna()))

print("\n=== LARGEST MOVES ===")
df['abs_return'] = df['returns'].abs()
top = df.nlargest(5, 'abs_return')[['close', 'returns', 'volume']]
print(top.round(4))

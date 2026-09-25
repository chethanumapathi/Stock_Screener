import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time as dtime

# Import amended and original strategies
import importlib.util

def load_module_from_file(filepath, modname):
    spec = importlib.util.spec_from_file_location(modname, filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

orig_mod = load_module_from_file('scratch/strong_buy_scan_current.py', 'orig')
amen_mod = load_module_from_file('scratch/strong_buy_scan_amended.py', 'amen')

print("Both modules imported successfully!")

# Let's create a synthetic test DataFrame with 5-minute bars over 6 days so lookbacks pass
dates = []
# 6 days of 5-min bars (09:15 to 15:30 -> 75 bars per day)
base_date = datetime(2026, 9, 14)
for day_offset in range(6):
    d = base_date + timedelta(days=day_offset)
    t = datetime(d.year, d.month, d.day, 9, 15)
    for _ in range(75):
        dates.append(t)
        t += timedelta(minutes=5)

n = len(dates)
df = pd.DataFrame({
    'date': dates,
    'open': [100.0] * n,
    'high': [101.0] * n,
    'low': [99.0] * n,
    'close': [100.0] * n,
    'volume': [10_000.0] * n,
    'market_cap_cr': [10_000.0] * n,
    'symbol': ['TEST'] * n
})

# Let's verify backtest runs on empty signal without errors
res_amen = amen_mod.backtest(df)
print("Backtest returned on baseline data:", len(res_amen['trades']), "trades.")

# Now test scenario B: breakout candle below Daily R3, then later candle closes above Daily R3
# Let's inspect simulate_trades directly
print("Testing simulate_trades directly...")
times = pd.date_range("2026-09-24 09:15", "2026-09-24 15:25", freq="5min")
m = len(times)
test_df = pd.DataFrame({
    'open': np.full(m, 100.0),
    'high': np.full(m, 101.0),
    'low': np.full(m, 99.0),
    'close': np.full(m, 100.0),
    'volume': np.full(m, 200_000.0),
}, index=times)

scan = np.zeros(m, dtype=bool)
scan[0] = True # 09:15 scan hit

# 09:15, 09:20, 09:25 is 15-min bucket -> bucket high = 101.0 (level = 101.0)
# 09:30 candle (idx=3): idx >= 09:30 -> state = WAIT_BRK
# At idx=4 (09:35): close = 102.0 > level (101.0), RSI = 85.0
# Daily R3 = 105.0. Since close (102.0) <= Daily R3 (105.0), it should transition to WAIT_R3!
# At idx=5 (09:40): close = 104.0 <= Daily R3 -> remains WAIT_R3
# At idx=6 (09:45): close = 106.0 > Daily R3 (105.0), high = 107.0 -> transitions to STOP_PENDING with stop=107.0!
# At idx=7 (09:50): high = 108.0 >= stop (107.0) -> ENTRY!

rsi = np.full(m, 50.0)
rsi[4] = 85.0

daily_r3 = np.full(m, 105.0)
vwap = np.full(m, 100.0)

test_df.loc[times[4], 'close'] = 102.0
test_df.loc[times[4], 'high'] = 103.0

test_df.loc[times[5], 'close'] = 104.0
test_df.loc[times[5], 'high'] = 104.5

test_df.loc[times[6], 'close'] = 106.0
test_df.loc[times[6], 'high'] = 107.0

test_df.loc[times[7], 'open'] = 106.0
test_df.loc[times[7], 'high'] = 108.0
test_df.loc[times[7], 'close'] = 107.5

trades, long_entry, tp_arr, extra = amen_mod.simulate_trades(test_df, scan, rsi, vwap, daily_r3)
print(f"Amended trades count: {len(trades)}")
for tr in trades:
    print("Trade:", tr)

# Check when long_entry happened:
entry_indices = np.where(long_entry)[0]
print("Entry indices:", entry_indices, "Time:", [times[k] for k in entry_indices])
assert len(entry_indices) == 1, "Should have exactly 1 entry"
assert entry_indices[0] == 7, f"Expected entry at candle idx 7 (09:50), got {entry_indices[0]}"
print("VERIFICATION SUCCESS: Entry occurred at idx 7 after candle idx 6 closed above Daily R3!")

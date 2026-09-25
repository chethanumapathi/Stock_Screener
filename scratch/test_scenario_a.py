import numpy as np
import pandas as pd
from datetime import time as dtime
import importlib.util

def load_module_from_file(filepath, modname):
    spec = importlib.util.spec_from_file_location(modname, filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

amen_mod = load_module_from_file('scratch/strong_buy_scan_amended.py', 'amen')

times = pd.date_range("2026-09-24 09:15", "2026-09-24 15:25", freq="5min")
m = len(times)

# Scenario A: Breakout candle itself is above Daily R3
test_df_a = pd.DataFrame({
    'open': np.full(m, 100.0),
    'high': np.full(m, 101.0),
    'low': np.full(m, 99.0),
    'close': np.full(m, 100.0),
    'volume': np.full(m, 200_000.0),
}, index=times)

scan_a = np.zeros(m, dtype=bool)
scan_a[0] = True # 09:15 scan hit (bucket high = 101.0)

rsi_a = np.full(m, 50.0)
rsi_a[4] = 85.0 # Breakout candle at idx 4

# Breakout candle close = 102.0 > Daily R3 (101.5)
daily_r3_a = np.full(m, 101.5)
vwap_a = np.full(m, 100.0)

test_df_a.loc[times[4], 'close'] = 102.0
test_df_a.loc[times[4], 'high'] = 103.0

# Next candle idx 5 trades above 103.0
test_df_a.loc[times[5], 'open'] = 102.5
test_df_a.loc[times[5], 'high'] = 103.5
test_df_a.loc[times[5], 'close'] = 103.0

trades_a, long_entry_a, tp_arr_a, extra_a = amen_mod.simulate_trades(test_df_a, scan_a, rsi_a, vwap_a, daily_r3_a)
entry_indices_a = np.where(long_entry_a)[0]
print("Scenario A Entry indices:", entry_indices_a, "Time:", [times[k] for k in entry_indices_a])
assert len(entry_indices_a) == 1 and entry_indices_a[0] == 5, f"Expected entry at idx 5, got {entry_indices_a}"
print("VERIFICATION SUCCESS: Scenario A immediately armed stop and entered at idx 5!")

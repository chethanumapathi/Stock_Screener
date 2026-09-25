import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, r"c:\Stock_Screener")

from strategies.intraday_rsi_volume_vwap_r2 import backtest, simulate_trades, evaluate_signals

print("=== Running Comprehensive Verification for 15-Minute Intraday Strategy ===")

def build_test_df():
    dates = []
    for d in pd.date_range("2026-09-18", "2026-09-24", freq="B"):
        day_times = pd.date_range(f"{d.strftime('%Y-%m-%d')} 09:15", f"{d.strftime('%Y-%m-%d')} 15:15", freq="15min")
        dates.extend(day_times)

    n = len(dates)
    df = pd.DataFrame(index=pd.DatetimeIndex(dates))
    df['open'] = 100.0
    df['high'] = 101.0
    df['low'] = 99.0
    df['close'] = 100.0
    df['volume'] = 50000.0

    for i in range(n):
        if i < 40:
            df.iloc[i, df.columns.get_loc('open')] = 90.0 + i * 0.1
            df.iloc[i, df.columns.get_loc('close')] = 90.0 + i * 0.1
            df.iloc[i, df.columns.get_loc('high')] = 91.0 + i * 0.1
            df.iloc[i, df.columns.get_loc('low')] = 89.0 + i * 0.1
        elif i < 50:
            df.iloc[i, df.columns.get_loc('open')] = 95.0
            df.iloc[i, df.columns.get_loc('close')] = 95.0
            df.iloc[i, df.columns.get_loc('high')] = 96.0
            df.iloc[i, df.columns.get_loc('low')] = 94.0

    df.iloc[54, df.columns.get_loc('close')] = 98.0
    df.iloc[54, df.columns.get_loc('high')] = 98.5
    df.iloc[54, df.columns.get_loc('low')] = 97.5

    # Bar 55 (Candle 1): Close=105, Vol=250k
    df.iloc[55, df.columns.get_loc('open')] = 98.0
    df.iloc[55, df.columns.get_loc('high')] = 106.0
    df.iloc[55, df.columns.get_loc('low')] = 98.0
    df.iloc[55, df.columns.get_loc('close')] = 105.0
    df.iloc[55, df.columns.get_loc('volume')] = 250000.0

    # Bar 56 (Candle 2): Close=112, Vol=300k
    df.iloc[56, df.columns.get_loc('open')] = 105.0
    df.iloc[56, df.columns.get_loc('high')] = 113.0
    df.iloc[56, df.columns.get_loc('low')] = 104.0
    df.iloc[56, df.columns.get_loc('close')] = 112.0
    df.iloc[56, df.columns.get_loc('volume')] = 300000.0
    return df

# 1. Test TP (+3%) Exit
print("\n--- Test 1: TP (+3.0%) Exit ---")
df1 = build_test_df()
# Bar 57 reaches TP (112 * 1.03 = 115.36)
df1.iloc[57, df1.columns.get_loc('open')] = 112.0
df1.iloc[57, df1.columns.get_loc('high')] = 116.0
df1.iloc[57, df1.columns.get_loc('low')] = 111.0
df1.iloc[57, df1.columns.get_loc('close')] = 115.5

res1 = backtest(df1)
trade1 = res1['trades'][0]
print("Trade 1 Exit:", trade1['exit_reason'], "Exit Price:", trade1['exit_price'])
assert "Target Profit" in trade1['exit_reason'], f"Expected TP exit, got {trade1['exit_reason']}"
assert trade1['exit_price'] == round(112.0 * 1.03, 2), f"Expected 115.36, got {trade1['exit_price']}"

# 2. Test Dynamic VWAP SL Exit
print("\n--- Test 2: Dynamic VWAP SL Exit ---")
df2 = build_test_df()
# On Bar 57: price closes below VWAP (e.g. VWAP is ~107 on bar 57, close at 104)
# Low is 103 -> this arms VWAP SL at 103!
df2.iloc[57, df2.columns.get_loc('open')] = 111.0
df2.iloc[57, df2.columns.get_loc('high')] = 111.5
df2.iloc[57, df2.columns.get_loc('low')] = 103.0
df2.iloc[57, df2.columns.get_loc('close')] = 104.0
df2.iloc[57, df2.columns.get_loc('volume')] = 100000.0

# On Bar 58: price drops and breaks below the armed low (103)
df2.iloc[58, df2.columns.get_loc('open')] = 103.5
df2.iloc[58, df2.columns.get_loc('high')] = 104.0
df2.iloc[58, df2.columns.get_loc('low')] = 101.0
df2.iloc[58, df2.columns.get_loc('close')] = 102.0

res2 = backtest(df2)
trade2 = res2['trades'][0]
print("Trade 2 Exit:", trade2['exit_reason'], "Exit Price:", trade2['exit_price'])
assert "Stop Loss (VWAP Breakdown Candle Low Broken)" in trade2['exit_reason'], f"Expected VWAP SL, got {trade2['exit_reason']}"
assert trade2['exit_price'] == 103.0, f"Expected 103.0, got {trade2['exit_price']}"

# 3. Test EOD Square-off Exit
print("\n--- Test 3: EOD Square-off (15:15) Exit ---")
df3 = build_test_df()
# From bar 57 to bar 74 (rest of the day), price stays above VWAP and below TP
for k in range(57, 75):
    df3.iloc[k, df3.columns.get_loc('open')] = 113.0
    df3.iloc[k, df3.columns.get_loc('high')] = 114.0 # under 115.36 TP
    df3.iloc[k, df3.columns.get_loc('low')] = 112.5  # above VWAP
    df3.iloc[k, df3.columns.get_loc('close')] = 113.5
    df3.iloc[k, df3.columns.get_loc('volume')] = 20000.0

res3 = backtest(df3)
trade3 = res3['trades'][0]
print("Trade 3 Exit:", trade3['exit_reason'], "Exit Date:", trade3['exit_date'])
assert "EOD Square-off" in trade3['exit_reason'], f"Expected EOD Square-off, got {trade3['exit_reason']}"
assert "15:15" in str(trade3['exit_date']), f"Expected 15:15 exit date, got {trade3['exit_date']}"

print("\nALL VERIFICATION TESTS (TP, DYNAMIC VWAP SL, EOD SQUARE-OFF) PASSED PERFECTLY!")

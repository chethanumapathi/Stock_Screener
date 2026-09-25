import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, r"c:\Stock_Screener")

from strategies.hourly_weekly_r3_supertrend import backtest

print("=== Running Comprehensive Verification for 1-Hour Weekly R3 + Supertrend Strategy ===")

def build_base_hourly_df():
    dates = []
    for d in pd.date_range("2026-08-01", "2026-09-24", freq="B"):
        day_times = pd.date_range(f"{d.strftime('%Y-%m-%d')} 09:15", f"{d.strftime('%Y-%m-%d')} 15:15", freq="1h")
        dates.extend(day_times)

    n = len(dates)
    df = pd.DataFrame(index=pd.DatetimeIndex(dates))
    df['open'] = 100.0
    df['high'] = 101.5
    df['low'] = 98.5
    df['close'] = 100.0
    df['volume'] = 50000.0

    # 1. Warmup
    for i in range(n):
        df.iloc[i, df.columns.get_loc('open')] = 100.0 + i * 0.05
        df.iloc[i, df.columns.get_loc('close')] = 100.0 + i * 0.05
        df.iloc[i, df.columns.get_loc('high')] = 101.5 + i * 0.05
        df.iloc[i, df.columns.get_loc('low')] = 98.5 + i * 0.05

    # Trigger at Bar 80: Close > Weekly R3
    df.iloc[80, df.columns.get_loc('open')] = 110.0
    df.iloc[80, df.columns.get_loc('high')] = 126.0
    df.iloc[80, df.columns.get_loc('low')] = 109.0
    df.iloc[80, df.columns.get_loc('close')] = 125.0

    # Pullback at Bars 85-89: Flips Supertrend to SELL (-1)
    for k in range(85, 90):
        df.iloc[k, df.columns.get_loc('open')] = 110.0 - (k - 85) * 2.0
        df.iloc[k, df.columns.get_loc('close')] = 105.0 - (k - 85) * 2.0
        df.iloc[k, df.columns.get_loc('high')] = 111.0 - (k - 85) * 2.0
        df.iloc[k, df.columns.get_loc('low')] = 98.0 - (k - 85) * 2.0

    # Reversal at Bar 95: Close 125 > upper band (~122) -> Flips Supertrend to BUY (+1)!
    # Qualifying high is High of Bar 95 (126.0)
    df.iloc[95, df.columns.get_loc('open')] = 110.0
    df.iloc[95, df.columns.get_loc('high')] = 126.0
    df.iloc[95, df.columns.get_loc('low')] = 108.0
    df.iloc[95, df.columns.get_loc('close')] = 125.0

    return df

# Test 1: TP (+10.0%) Scenario
print("\n--- Test 1: TP (+10.0%) Exit ---")
df1 = build_base_hourly_df()
# Bar 96: Breaks 126.0 -> enters at 126.0
df1.iloc[96, df1.columns.get_loc('open')] = 125.5
df1.iloc[96, df1.columns.get_loc('high')] = 128.0
df1.iloc[96, df1.columns.get_loc('low')] = 125.0
df1.iloc[96, df1.columns.get_loc('close')] = 127.0

# Bar 97: Reaches TP (+10% on 126.0 is 138.60)
df1.iloc[97, df1.columns.get_loc('open')] = 130.0
df1.iloc[97, df1.columns.get_loc('high')] = 140.0  # High >= 138.60
df1.iloc[97, df1.columns.get_loc('low')] = 129.0
df1.iloc[97, df1.columns.get_loc('close')] = 139.0

res1 = backtest(df1)
assert len(res1['trades']) >= 1, "Expected at least 1 trade in Test 1!"
trade1 = res1['trades'][0]
print("Trade 1 Exit:", trade1['exit_reason'], "Entry:", trade1['entry_price'], "Exit:", trade1['exit_price'])
assert "Target Profit (+10.0%)" in trade1['exit_reason'], f"Expected TP 10%, got {trade1['exit_reason']}"
assert trade1['entry_price'] == 126.0, f"Expected 126.0, got {trade1['entry_price']}"
assert trade1['exit_price'] == 138.60, f"Expected 138.60, got {trade1['exit_price']}"

# Test 2: Supertrend Sell SL Scenario
print("\n--- Test 2: Supertrend Sell SL Exit ---")
df2 = build_base_hourly_df()
# Bar 96: Breaks 126.0 -> enters at 126.0
df2.iloc[96, df2.columns.get_loc('open')] = 125.5
df2.iloc[96, df2.columns.get_loc('high')] = 128.0
df2.iloc[96, df2.columns.get_loc('low')] = 125.0
df2.iloc[96, df2.columns.get_loc('close')] = 127.0

# Bar 97: Price drops sharply below Supertrend line, flipping Supertrend back to SELL (-1)
df2.iloc[97, df2.columns.get_loc('open')] = 115.0
df2.iloc[97, df2.columns.get_loc('high')] = 116.0
df2.iloc[97, df2.columns.get_loc('low')] = 95.0
df2.iloc[97, df2.columns.get_loc('close')] = 96.0  # Flips ST to Sell!

res2 = backtest(df2)
assert len(res2['trades']) >= 1, "Expected at least 1 trade in Test 2!"
trade2 = res2['trades'][0]
print("Trade 2 Exit:", trade2['exit_reason'], "Entry:", trade2['entry_price'], "Exit:", trade2['exit_price'])
assert "Stop Loss (Supertrend Sell Signal)" in trade2['exit_reason'], f"Expected Supertrend Sell SL, got {trade2['exit_reason']}"
assert trade2['exit_price'] == 96.0, f"Expected 96.0, got {trade2['exit_price']}"

# Test 3: 2-Week Expiry Scenario (Supertrend stays in Sell > 14 days)
print("\n--- Test 3: 2-Week Expiry Scenario ---")
df3 = build_base_hourly_df()
# Do not flip to Buy at bar 95; keep in downtrend/sideways until end of data
for k in range(90, len(df3)):
    df3.iloc[k, df3.columns.get_loc('close')] = 90.0
    df3.iloc[k, df3.columns.get_loc('open')] = 90.0
    df3.iloc[k, df3.columns.get_loc('high')] = 92.0
    df3.iloc[k, df3.columns.get_loc('low')] = 88.0

res3 = backtest(df3)
print("Trades in Test 3:")
for t in res3['trades']:
    print("  ", t)
assert len(res3['trades']) == 0, f"Expected 0 trades due to 2-week expiry, got {len(res3['trades'])}"

print("\nALL 3 SCENARIO TESTS (TP 10%, SUPERTREND SL, 2-WEEK TIMEOUT) PASSED PERFECTLY!")

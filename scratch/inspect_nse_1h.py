import sys
sys.path.insert(0, '.')
import duckdb
import pandas as pd
import numpy as np
from app import get_ticker_parquet_path
from strategies.fifteen_min_weekly_r3_r2_rsi80 import _prepare_5min_df, compute_weekly_pivots

p = get_ticker_parquet_path('FINCABLES')
con = duckdb.connect()
df_raw = con.execute(f"SELECT * FROM '{p}' ORDER BY Date").df()
con.close()

df_5m = _prepare_5min_df(df_raw)

# Method 1: Daily grouping and binning by 1-hour market intervals
def construct_nse_1hour_candles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Constructs genuine NSE 1-hour candles anchored at 09:15 IST:
    Bar 1: 09:15 - 10:15
    Bar 2: 10:15 - 11:15
    Bar 3: 11:15 - 12:15
    Bar 4: 12:15 - 13:15
    Bar 5: 13:15 - 14:15
    Bar 6: 14:15 - 15:15
    Bar 7: 15:15 - 15:30 (remaining 15 mins)
    """
    # Define hour slot based on minutes elapsed since 09:15
    times = df.index
    mins_from_midnight = times.hour * 60 + times.minute
    m_open = 9 * 60 + 15  # 555
    
    # Intraday minute offset
    diff_mins = np.maximum(0, mins_from_midnight - m_open)
    hour_slot = diff_mins // 60  # 0 for 9:15-10:14, 1 for 10:15-11:14, etc.
    
    day_series = times.normalize()
    # Group by (day, hour_slot)
    grouped = df.groupby([day_series, hour_slot]).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    })
    
    # Construct timestamp for each bar (the start timestamp)
    bar_times = []
    for (day, slot), _ in grouped.iterrows():
        start_min = m_open + slot * 60
        shour = start_min // 60
        smin = start_min % 60
        bar_times.append(day.replace(hour=shour, minute=smin))
        
    res = grouped.copy()
    res.index = pd.DatetimeIndex(bar_times)
    return res.sort_index()

df_1h = construct_nse_1hour_candles(df_5m)
print("Total 1-hour candles:", len(df_1h))

_, r3_1h = compute_weekly_pivots(df_1h)

# Check May 4 to May 8
print("\n--- Genuine NSE 1-Hour Candles (May 4 - 8, 2026) ---")
for idx, row in df_1h.iterrows():
    if idx >= pd.Timestamp('2026-05-04') and idx <= pd.Timestamp('2026-05-09'):
        loc = df_1h.index.get_loc(idx)
        w_r3 = r3_1h[loc]
        above = row['close'] > w_r3
        # Closing time: for slots 0-5 it's +60 mins, for slot 6 it's +15 mins
        close_min = 15 if (idx.hour == 15 and idx.minute == 15) else 60
        closing_time = idx + pd.Timedelta(minutes=close_min)
        print(f"Bar: {idx.strftime('%Y-%m-%d %H:%M')} -> Closes at {closing_time.strftime('%H:%M')} | Close: {row['close']:.2f} | Weekly R3: {w_r3:.2f} | Above: {above}")

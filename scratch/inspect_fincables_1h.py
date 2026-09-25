import sys
sys.path.insert(0, '.')
import duckdb
import pandas as pd
from app import get_ticker_parquet_path
from strategies.fifteen_min_weekly_r3_r2_rsi80 import _prepare_5min_df, compute_weekly_pivots

p = get_ticker_parquet_path('FINCABLES')
con = duckdb.connect()
df_raw = con.execute(f"SELECT * FROM '{p}' ORDER BY Date").df()
con.close()

df_5m = _prepare_5min_df(df_raw)
r2, r3 = compute_weekly_pivots(df_5m)

# Find weekly pivot values for week of 2026-05-04 to 2026-05-08
may_mask = (df_5m.index >= '2026-05-01') & (df_5m.index <= '2026-05-10')
print("Weekly R2 on 07-May-2026:", r2[may_mask][-1])
print("Weekly R3 on 07-May-2026:", r3[may_mask][-1])

# Resample using Indian market hours offset (starting at 09:15)
# In pandas: resample('1h', offset='15min', closed='left', label='left')
df_1h_nse = df_5m.resample('1h', offset='15min', closed='left', label='left').agg({
    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
}).dropna()

_, r3_1h = compute_weekly_pivots(df_1h_nse)

print("\n--- 1-Hour Candles (NSE 09:15 alignment) May 4-8 ---")
for idx, row in df_1h_nse.iterrows():
    if idx >= pd.Timestamp('2026-05-04') and idx <= pd.Timestamp('2026-05-09'):
        w_r3 = r3_1h[df_1h_nse.index.get_loc(idx)]
        above = row['close'] > w_r3
        print(f"{idx} -> Open: {row['open']:.2f}, High: {row['high']:.2f}, Low: {row['low']:.2f}, Close: {row['close']:.2f} | Weekly R3: {w_r3:.2f} | Above: {above}")

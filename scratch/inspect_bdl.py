import sys, os
sys.path.insert(0, os.path.abspath('.'))
from strategies.fifteen_min_weekly_r3_r2_rsi80 import backtest
from app import get_ticker_parquet_path
import duckdb

p = get_ticker_parquet_path('BDL')
con = duckdb.connect()
df_raw = con.execute(f"SELECT * FROM '{p}' WHERE date >= '2025-03-15' AND date <= '2025-03-25' ORDER BY date").df()
con.close()

res = backtest(df_raw)
for t in res['trades']:
    print(t)

df_5m = res['df']
day_bars = df_5m[(df_5m.index >= '2025-03-19 11:45') & (df_5m.index <= '2025-03-20 09:30')]
print("\nBDL 5m Bars around trade:")
for idx, row in day_bars.iterrows():
    print(f"{idx} | O: {row['open']:.2f}, H: {row['high']:.2f}, L: {row['low']:.2f}, C: {row['close']:.2f}, VWAP: {row['VWAP']:.2f}")

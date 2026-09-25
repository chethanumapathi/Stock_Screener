import os
import sys
sys.path.insert(0, os.path.abspath('.'))
import duckdb
import pandas as pd
import numpy as np
from app import get_ticker_parquet_path
from strategies.fifteen_min_weekly_r3_r2_rsi80 import backtest, _prepare_5min_df, compute_session_vwap

p = get_ticker_parquet_path('ELECON')
con = duckdb.connect()
df_raw = con.execute(f"SELECT * FROM '{p}' WHERE date >= '2026-05-01' ORDER BY date").df()
con.close()

res = backtest(df_raw)
trades = [t for t in res['trades'] if '2026-05-06' in str(t['entry_date'])]
print("ELECON Trades on 2026-05-06:")
for t in trades:
    print(t)

df_5m = res['df']
day_bars = df_5m[(df_5m.index >= '2026-05-06 09:15') & (df_5m.index <= '2026-05-06 11:30')]
print("\nELECON 5m Bars on 2026-05-06:")
for idx, row in day_bars.iterrows():
    print(f"{idx} | O: {row['open']:.2f}, H: {row['high']:.2f}, L: {row['low']:.2f}, C: {row['close']:.2f}, VWAP: {row['VWAP']:.2f}, R2: {row['Weekly_R2']:.2f}, RSI: {row['RSI_5m']:.2f}, Signal: {row['Signal']}, Short_Entry: {row['Short_Entry']}")

import os
import duckdb
import pandas as pd

symbols = ['TTML', 'GESHIP', 'AEQUS']
for s in symbols:
    p1 = f'data/minute/{s}.parquet'
    p2 = rf'C:\Zerodha Historical Data\data\minute\{s}.parquet'
    chosen = p1 if os.path.exists(p1) else (p2 if os.path.exists(p2) else None)
    print(f'Symbol: {s}, exists: {chosen}')
    if chosen:
        con = duckdb.connect()
        df = con.execute(f"SELECT min(date), max(date), count(1) FROM '{chosen}'").df()
        print('  Range:', df.values[0])
        today_df = con.execute(f"SELECT date, open, high, low, close, volume FROM '{chosen}' WHERE CAST(date AS VARCHAR) LIKE '2026-09-28%' ORDER BY date DESC").df()
        print('  Today count:', len(today_df))
        if not today_df.empty:
            print('  Today latest:', today_df.head(2).to_dict(orient='records'))
        else:
            print('  *** NO DATA FOR TODAY (2026-09-28) IN PARQUET! ***')

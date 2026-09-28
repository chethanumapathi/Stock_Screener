import glob
import os
import duckdb
import pandas as pd

con = duckdb.connect()
files = glob.glob(r"C:\Stock_Screener\data\minute\*.parquet")
print(f"Total parquet files: {len(files)}")

today_counts = 0
today_stocks = []

for f in files:
    sym = os.path.basename(f).replace('.parquet', '')
    res = con.execute("SELECT max(date) as max_d, count(*) FILTER (WHERE CAST(date AS DATE) = '2026-09-28') as cnt FROM read_parquet(?)", [f]).fetchone()
    if res and res[1] > 0:
        today_counts += 1
        today_stocks.append((sym, res[0], res[1]))

print(f"Stocks with 2026-09-28 data: {today_counts}")
print("Sample stocks with today's data:", today_stocks[:10])

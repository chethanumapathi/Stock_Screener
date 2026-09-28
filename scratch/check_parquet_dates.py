import duckdb
import os
import glob
import pandas as pd

p = r"C:\Stock_Screener\data\minute\RELIANCE.parquet"
con = duckdb.connect()
df = con.execute("SELECT max(date) as max_d, min(date) as min_d, count(*) as cnt FROM read_parquet(?)", [p]).fetchdf()
print("RELIANCE:", df)

# Check some other tickers
for sym in ['HDFCBANK', 'TCS', 'INFY', 'ICICIBANK']:
    p = f"C:/Stock_Screener/data/minute/{sym}.parquet"
    if os.path.exists(p):
        d = con.execute("SELECT max(date) FROM read_parquet(?)", [p]).fetchall()
        print(sym, d)

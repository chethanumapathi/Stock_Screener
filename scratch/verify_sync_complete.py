import duckdb
import glob
import os

con = duckdb.connect()

# 1. Check minute data
min_files = glob.glob(r"C:\Zerodha Historical Data\data\minute\*.parquet")
print(f"Total Minute Parquet Files: {len(min_files)}")

sample_minute_stocks = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'TATAMOTORS', 'ZUARI', 'ZUARIIND']
for sym in sample_minute_stocks:
    p = rf"C:\Zerodha Historical Data\data\minute\{sym}.parquet"
    if os.path.exists(p):
        r = con.execute("SELECT MIN(date)::VARCHAR, MAX(date)::VARCHAR, COUNT(*) FROM read_parquet(?)", [p]).fetchone()
        print(f"  [1-Min] {sym:<12}: Min = {r[0]} | Max = {r[1]} | Rows = {r[2]:,}")

# 2. Check adjusted daily cache
daily_files = glob.glob("data/adjusted_daily/*.parquet")
print(f"\nTotal Pre-Adjusted Daily Files: {len(daily_files)}")

for sym in sample_minute_stocks:
    p = f"data/adjusted_daily/{sym}.parquet"
    if os.path.exists(p):
        r = con.execute("SELECT MIN(date)::VARCHAR, MAX(date)::VARCHAR, COUNT(*) FROM read_parquet(?)", [p]).fetchone()
        print(f"  [Daily] {sym:<12}: Min = {r[0]} | Max = {r[1]} | Days = {r[2]:,}")

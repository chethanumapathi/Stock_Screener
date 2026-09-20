import duckdb
import glob
import os

con = duckdb.connect()
path = r"C:\Zerodha Historical Data\data\minute\RELIANCE.parquet"
if os.path.exists(path):
    res = con.execute("SELECT MIN(date), MAX(date), count(1) FROM read_parquet(?)", [path]).fetchall()
    print("RELIANCE.parquet:", res)
else:
    print("Path does not exist:", path)

# Check a few other symbols
for sym in ['TCS', 'INFY', 'HDFCBANK']:
    p = rf"C:\Zerodha Historical Data\data\minute\{sym}.parquet"
    if os.path.exists(p):
        res = con.execute("SELECT MIN(date), MAX(date), count(1) FROM read_parquet(?)", [p]).fetchall()
        print(f"{sym}.parquet:", res)

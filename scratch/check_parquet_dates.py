import os
import duckdb
import pandas as pd

local_dir = r'C:\Stock_Screener\data\minute'
zerodha_dir = r'C:\Zerodha Historical Data\data\minute'

print(f"local_dir exists: {os.path.exists(local_dir)}, files: {len(os.listdir(local_dir)) if os.path.exists(local_dir) else 0}")
print(f"zerodha_dir exists: {os.path.exists(zerodha_dir)}, files: {len(os.listdir(zerodha_dir)) if os.path.exists(zerodha_dir) else 0}")

con = duckdb.connect()
for s in ['TCI', 'SPARC', 'ARTEMISMED', 'LLOYDSENGG', 'LLOYDSENT', 'LCL']:
    lp = os.path.join(local_dir, f'{s}.parquet')
    zp = os.path.join(zerodha_dir, f'{s}.parquet')
    print(f"\nStock {s}: local={os.path.exists(lp)}, zerodha={os.path.exists(zp)}")
    if os.path.exists(lp):
        max_d = con.execute(f"SELECT max(Date), min(Date), count(Date) FROM read_parquet('{lp}')").fetchone()
        print(f"   Local: min={max_d[1]}, max={max_d[0]}, count={max_d[2]}")
    if os.path.exists(zp):
        max_d = con.execute(f"SELECT max(Date), min(Date), count(Date) FROM read_parquet('{zp}')").fetchone()
        print(f"   Zerodha: min={max_d[1]}, max={max_d[0]}, count={max_d[2]}")

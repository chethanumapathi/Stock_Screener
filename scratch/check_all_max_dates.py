import duckdb
import glob
import os
from collections import Counter
from datetime import datetime

con = duckdb.connect()
files = glob.glob(r"C:\Zerodha Historical Data\data\minute\*.parquet")
print(f"Total parquet files found: {len(files)}")

date_counter = Counter()
stocks_by_date = {}

for idx, f in enumerate(files):
    sym = os.path.splitext(os.path.basename(f))[0]
    try:
        r = con.execute("SELECT MAX(CAST(date AS DATE))::VARCHAR FROM read_parquet(?)", [f]).fetchone()
        d = r[0] if r and r[0] else 'None'
    except Exception as e:
        d = f"Error: {e}"
    
    date_counter[d] += 1
    if d not in stocks_by_date:
        stocks_by_date[d] = []
    if len(stocks_by_date[d]) < 10:
        stocks_by_date[d].append(sym)

print("\n--- Max Date Distribution across ALL Parquet files ---")
for d, count in sorted(date_counter.items(), key=lambda x: str(x[0]), reverse=True):
    examples = ", ".join(stocks_by_date[d][:5])
    print(f"Date: {d} -> Count: {count} stocks (Examples: {examples})")

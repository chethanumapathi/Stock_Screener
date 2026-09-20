import duckdb
import glob
import os

con = duckdb.connect()
files = glob.glob(r"C:\Zerodha Historical Data\data\minute\*.parquet")
print(f"Total parquet files: {len(files)}")

date_counts = {}
sample_files = files[:100]  # sample 100 first to be fast
for f in sample_files:
    sym = os.path.splitext(os.path.basename(f))[0]
    try:
        r = con.execute("SELECT MAX(CAST(date AS DATE))::VARCHAR FROM read_parquet(?)", [f]).fetchone()
        md = r[0] if r else 'None'
        date_counts[md] = date_counts.get(md, 0) + 1
    except Exception as e:
        date_counts['error'] = date_counts.get('error', 0) + 1

print("Sample (100 files) max date distribution:", date_counts)

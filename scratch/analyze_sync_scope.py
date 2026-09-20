import glob
import os
import duckdb

con = duckdb.connect()
files = glob.glob(r"C:\Zerodha Historical Data\data\minute\*.parquet")
print(f"Total parquet files: {len(files)}")

date_summary = {}
need_sync = []

for idx, f in enumerate(files):
    sym = os.path.splitext(os.path.basename(f))[0]
    try:
        r = con.execute("SELECT MAX(CAST(date AS DATE))::VARCHAR FROM read_parquet(?)", [f]).fetchone()
        md = r[0] if r else 'None'
        date_summary[md] = date_summary.get(md, 0) + 1
        if md < '2026-09-18':
            need_sync.append((sym, md))
    except Exception as e:
        date_summary['error'] = date_summary.get('error', 0) + 1

print("\nDate Summary across all files:")
for k, v in sorted(date_summary.items()):
    print(f"  {k}: {v} files")

print(f"\nTotal files needing sync to 18th Sep: {len(need_sync)}")

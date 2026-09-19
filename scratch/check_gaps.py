import os, glob, duckdb

data_dir = r"C:\Zerodha Historical Data\data\minute"
files = glob.glob(os.path.join(data_dir, "*.parquet"))
print(f"Total files in minute dir: {len(files)}")

con = duckdb.connect()
need_sync = []
for f in files:
    sym = os.path.basename(f).replace(".parquet", "")
    try:
        p_clean = f.replace("\\", "/")
        query = "SELECT min(date), max(date), count(*) FROM '" + p_clean + "'"
        res = con.execute(query).fetchone()
        min_dt = str(res[0])[:10] if res[0] else None
        max_dt = str(res[1])[:10] if res[1] else None
        cnt = res[2]
        if min_dt and min_dt > "2021-09-25":
            need_sync.append((sym, min_dt, max_dt, cnt))
    except Exception as e:
        pass

print(f"Total stocks in minute dir: {len(files)}")
print(f"Stocks starting after 2021-09-25 (potential missing history): {len(need_sync)}")
for s, min_d, max_d, c in need_sync[:30]:
    print(f"{s:15} Starts: {min_d}  Ends: {max_d}  Rows: {c}")

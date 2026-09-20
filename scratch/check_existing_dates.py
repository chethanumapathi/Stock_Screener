import duckdb

con = duckdb.connect()
path = r"C:\Zerodha Historical Data\data\minute\RELIANCE.parquet"
res = con.execute("""
    SELECT DISTINCT CAST(date AS DATE)::VARCHAR as d, count(1) as cnt 
    FROM read_parquet(?) 
    WHERE CAST(date AS VARCHAR) >= '2026-09-01' 
    GROUP BY d 
    ORDER BY d
""", [path]).fetchall()

print("Dates in RELIANCE.parquet >= 2026-09-01:")
for r in res:
    print(" ", r)

# Let's also check across a few other tickers
for s in ['TCS', 'INFY', 'SBIN', 'HDFCBANK', 'ICICIBANK']:
    p = rf"C:\Zerodha Historical Data\data\minute\{s}.parquet"
    r = con.execute("""
        SELECT MAX(CAST(date AS DATE))::VARCHAR 
        FROM read_parquet(?)
    """, [p]).fetchone()
    print(f"Max date for {s}: {r[0]}")

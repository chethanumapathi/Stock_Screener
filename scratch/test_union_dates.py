import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app, duckdb

con = app.get_duckdb_connection()
p_daily = os.path.join(app.ADJUSTED_DAILY_DIR, 'RELIANCE.parquet')
p_min = app.get_ticker_parquet_path('RELIANCE')
sources = []
if p_daily and os.path.exists(p_daily):
    sources.append(f"SELECT DISTINCT CAST(date AS DATE)::VARCHAR as d FROM read_parquet('{p_daily.replace('\\', '/')}')")
if p_min and os.path.exists(p_min):
    sources.append(f"SELECT DISTINCT CAST(date AS DATE)::VARCHAR as d FROM read_parquet('{p_min.replace('\\', '/')}')")
union_sql = " UNION ".join(sources) + " ORDER BY d DESC"
dates = con.execute(union_sql).fetchdf()['d'].tolist()
print("Dates count:", len(dates), "Top 5:", dates[:5])

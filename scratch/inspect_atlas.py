import sys, os
sys.path.insert(0, os.path.abspath('.'))
from strategies.fifteen_min_weekly_r3_r2_rsi80 import backtest
from app import get_ticker_parquet_path
import duckdb

p = get_ticker_parquet_path('ATLASCYCLE')
con = duckdb.connect()
df_raw = con.execute(f"SELECT * FROM '{p}' WHERE date >= '2025-01-01' AND date <= '2025-01-15' ORDER BY date").df()
con.close()

res = backtest(df_raw)
for t in res['trades']:
    print(t)

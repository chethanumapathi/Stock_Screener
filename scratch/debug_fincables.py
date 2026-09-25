import sys
sys.path.insert(0, '.')
import duckdb
import pandas as pd
from app import get_ticker_parquet_path
from strategies.fifteen_min_weekly_r3_r2_rsi80 import backtest, _prepare_5min_df, compute_1hour_triggers, compute_weekly_pivots

p = get_ticker_parquet_path('FINCABLES')
print('Path:', p)
if p:
    con = duckdb.connect()
    df_raw = con.execute(f"SELECT * FROM '{p}' ORDER BY Date").df()
    con.close()
    print('Raw rows:', len(df_raw))
    df_5m = _prepare_5min_df(df_raw)
    print('5m rows:', len(df_5m))
    trig_times = compute_1hour_triggers(df_5m)
    print('Triggers around April-May 2026:')
    for t in trig_times:
        if '2026-05' in str(t) or '2026-04' in str(t):
            print(' Trigger at:', t)
            
    res = backtest(df_raw)
    print('\nAll Trades in May 2026:')
    for tr in res['trades']:
        if '2026-05' in str(tr['entry_date']):
            print(' Trade:', tr)

import sys
sys.path.insert(0, r"c:\Stock_Screener")
import fetch_kotak_history as fkh
import pandas as pd
import duckdb
import os
import time

cfg = fkh.load_env_config('kotak_credentials.env')
client_mgr = fkh.KotakClientManager(cfg)
scrip = fkh.ScripResolver(client_mgr)

symbols = ['OPTIEMUS', 'SOUTHBANK']

for sym in symbols:
    print(f"\nRepairing {sym}...")
    tok = scrip.get_token(sym)
    res = client_mgr.fetch_historical_candles(tok, '1min', '2026-09-21', '2026-09-25')
    candles = res.get('data', {}).get('candles', []) if isinstance(res, dict) else []
    print(f"  Fetched {len(candles)} clean 1-minute candles from Kotak.")
    
    clean_rows = []
    for c in candles:
        dt = c[0][:19].replace('T', ' ')
        clean_rows.append({
            'date': pd.to_datetime(dt),
            'open': float(c[1]),
            'high': float(c[2]),
            'low': float(c[3]),
            'close': float(c[4]),
            'volume': float(c[5])
        })
    df_clean = pd.DataFrame(clean_rows)
    
    p_file = rf"c:\Stock_Screener\data\minute\{sym}.parquet"
    con = duckdb.connect()
    df_orig = con.execute(f"SELECT date, open, high, low, close, volume FROM read_parquet('{p_file}') WHERE date < TIMESTAMP '2026-09-21 00:00:00'").df()
    df_merged = pd.concat([df_orig, df_clean]).drop_duplicates(subset=['date']).sort_values('date').reset_index(drop=True)
    df_merged.to_parquet(p_file, index=False)
    print(f"  Saved repaired {sym}.parquet! Total rows: {len(df_merged)}")
    time.sleep(0.5)

print("\nRepair completed!")

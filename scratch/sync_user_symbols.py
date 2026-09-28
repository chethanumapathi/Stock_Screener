import os
import sys
sys.path.insert(0, os.path.abspath('.'))
import time
import pandas as pd
import fetch_kotak_history as fkh
import duckdb

cfg = fkh.load_env_config('kotak_credentials.env')
cm = fkh.KotakClientManager(cfg)
sr = fkh.ScripResolver(cm)

symbols = ['TTML', 'GESHIP', 'AEQUS']
for sym in symbols:
    clean_sym = sym.strip().upper()
    tok = sr.get_token(clean_sym)
    print(f"\n--- Syncing {clean_sym} ({tok}) for 2026-09-28 ---")
    p_file = f"data/minute/{clean_sym}.parquet"
    
    res = cm.fetch_historical_candles(
        neo_symbol=tok,
        interval="1min",
        from_date="2026-09-28",
        to_date="2026-09-28"
    )
    df = fkh.parse_candles_to_df(res)
    print(f"Fetched {len(df)} candles for {clean_sym}")
    if not df.empty:
        ok, total_rows, msg = fkh.stitch_and_save_parquet(p_file, df, symbol=clean_sym)
        print(f"Stitch result: ok={ok}, total_rows={total_rows}, msg={msg}")
    time.sleep(1.0)

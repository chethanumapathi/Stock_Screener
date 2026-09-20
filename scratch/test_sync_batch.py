import sys
sys.path.insert(0, '.')
import os
import duckdb
import fetch_kotak_history as fkh

config = fkh.load_env_config("kotak_credentials.env")
client_mgr = fkh.KotakClientManager(config)
scrip_resolver = fkh.ScripResolver(client_mgr)

test_symbols = ['RELIANCE', 'TCS', 'SBIN', 'HDFCBANK', 'ICICIBANK']
data_dir = r"C:\Zerodha Historical Data\data\minute"

for sym in test_symbols:
    p_file = os.path.join(data_dir, f"{sym}.parquet")
    min_dt, max_dt, count = fkh.inspect_existing_file(p_file)
    print(f"\nProcessing {sym}: current max={max_dt}, rows={count}")
    
    if max_dt and max_dt.strftime('%Y-%m-%d') >= '2026-09-18':
        print(f"  -> {sym} is already up to date through 18th Sep. Skipping.")
        continue
        
    token = scrip_resolver.get_token(sym)
    if not token:
        print(f"  -> Token not found for {sym}")
        continue
        
    from_date = (max_dt + fkh.timedelta(days=1)).strftime('%Y-%m-%d') if max_dt else '2026-09-12'
    to_date = '2026-09-19'
    print(f"  -> Fetching {token} from {from_date} to {to_date}...")
    
    res = client_mgr.fetch_historical_candles(token, "1min", from_date, to_date)
    df_chunk = fkh.parse_candles_to_df(res)
    print(f"  -> Returned {len(df_chunk)} candles.")
    
    if not df_chunk.empty:
        ok, total_rows, msg = fkh.stitch_and_save_parquet(p_file, df_chunk)
        new_min, new_max, new_cnt = fkh.inspect_existing_file(p_file)
        print(f"  -> Stitched: ok={ok}, new max={new_max}, total_rows={new_cnt}")
    else:
        print("  -> No candles returned.")

import sys
sys.path.insert(0, '.')
import os
import duckdb
import fetch_kotak_history as fkh

config = fkh.load_env_config("kotak_credentials.env")
client_mgr = fkh.KotakClientManager(config)
scrip_resolver = fkh.ScripResolver(client_mgr)

symbol = "INFY"
p_file = rf"C:\Zerodha Historical Data\data\minute\{symbol}.parquet"
min_dt, max_dt, count = fkh.inspect_existing_file(p_file)
print(f"Before INFY: min={min_dt}, max={max_dt}, count={count}")

neo_token = scrip_resolver.get_token(symbol)
print(f"Token for {symbol}: {neo_token}")

res = client_mgr.fetch_historical_candles(neo_token, "1min", "2026-09-12", "2026-09-19")
df_chunk = fkh.parse_candles_to_df(res)
print(f"Fetched {len(df_chunk)} candles for {symbol}")

if not df_chunk.empty:
    ok, total_rows, msg = fkh.stitch_and_save_parquet(p_file, df_chunk)
    print(f"Stitch result: ok={ok}, total_rows={total_rows}, msg={msg}")
    min_dt2, max_dt2, count2 = fkh.inspect_existing_file(p_file)
    print(f"After INFY: min={min_dt2}, max={max_dt2}, count={count2}")

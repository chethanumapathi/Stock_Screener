import sys
sys.path.insert(0, '.')
import os
import duckdb
import fetch_kotak_history as fkh

config = fkh.load_env_config("kotak_credentials.env")
client_mgr = fkh.KotakClientManager(config)
scrip_resolver = fkh.ScripResolver(client_mgr)

# Check Nifty 50
n50_file = "data/nifty50.csv"
n50_syms = []
if os.path.exists(n50_file):
    import pandas as pd
    df = pd.read_csv(n50_file)
    n50_syms = df['Symbol'].dropna().str.strip().tolist()

missing_tokens = []
found_tokens = []
for s in n50_syms:
    t = scrip_resolver.get_token(s)
    if t:
        found_tokens.append((s, t))
    else:
        missing_tokens.append(s)

print(f"Nifty 50 Token Coverage: {len(found_tokens)}/{len(n50_syms)} found.")
if missing_tokens:
    print("Missing Nifty 50 tokens:", missing_tokens)

# Check all 2,294 parquet files
import glob
files = glob.glob(r"C:\Zerodha Historical Data\data\minute\*.parquet")
all_syms = [os.path.splitext(os.path.basename(f))[0] for f in files]

missing_all = []
found_all = []
for s in all_syms:
    t = scrip_resolver.get_token(s)
    if t:
        found_all.append((s, t))
    else:
        missing_all.append(s)

print(f"All Parquet Files Token Coverage: {len(found_all)}/{len(all_syms)} found ({len(found_all)/len(all_syms)*100:.1f}%).")
if missing_all:
    print(f"Missing from master ({len(missing_all)} stocks):", missing_all[:15])

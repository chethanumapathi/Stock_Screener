import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

symbols = app.fetch_nifty500_symbols()
print(f"Loaded {len(symbols)} symbols from Nifty 500.")

with open('data/strategies.json', 'r', encoding='utf-8') as f:
    strategies = app.json.load(f)
code_str = [s['code'] for s in strategies if 'Strong buy' in s['name']][0]

exec_env = {
    'pd': pd,
    'np': np,
    'datetime': app.datetime,
    'timedelta': app.timedelta,
    'get_market_cap_cr': app.get_market_cap_cr,
    'get_stock_fundamentals': app.get_stock_fundamentals,
}
exec(code_str, exec_env)
screen_func = exec_env['screen']

timeframe = '5m'
end_date = '2026-09-22'
start_date = '2026-09-22'
min_market_cap_cr = 5000.0

ref_dt = pd.to_datetime(end_date) if end_date else pd.Timestamp.now()
if start_date:
    try:
        ref_dt = min(ref_dt, pd.to_datetime(start_date))
    except Exception:
        pass
effective_start = (ref_dt - pd.Timedelta(days=60)).strftime('%Y-%m-%d')

def evaluate_symbol(sym):
    try:
        mcap = app.get_market_cap_cr(sym, fetch_online=False)
        if min_market_cap_cr > 0 and mcap > 0 and mcap < min_market_cap_cr:
            return sym, []
        df_sym = app.get_ticker_data_duckdb(sym, timeframe=timeframe, start_date=effective_start, end_date=end_date)
        if df_sym.empty:
            return sym, []
        res = screen_func(df_sym)
        sig = res.get('signal') if isinstance(res, dict) else res
        if sig is None or not (sig == True).any():
            return sym, []
        
        matches = []
        match_idx = df_sym.index[sig == True]
        for idx in match_idx:
            row = df_sym.loc[idx]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            d_str = str(row['Date'])
            if start_date and d_str[:10] < str(start_date)[:10]:
                continue
            if end_date and d_str[:10] > str(end_date)[:10]:
                continue
            matches.append({
                'Date': d_str,
                'Symbol': sym,
                'Close': float(row['Close']),
                'Volume': int(row['Volume']),
                'Market_Cap_Cr': float(mcap)
            })
        return sym, matches
    except Exception as e:
        return sym, []

t0 = time.time()
total_matches = 0
all_matches = []

with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(evaluate_symbol, symbols))

for sym, matches in results:
    if matches:
        total_matches += len(matches)
        all_matches.extend(matches)

elapsed = time.time() - t0
print(f"Screened {len(symbols)} symbols in {elapsed:.2f} seconds!")
print(f"Total signals found: {total_matches}")
for m in all_matches:
    print(f"  {m['Date']} [{m['Symbol']}] Close={m['Close']} Vol={m['Volume']}")

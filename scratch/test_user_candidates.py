import os, sys
sys.path.insert(0, os.path.abspath('.'))
import pandas as pd
import numpy as np
import app

symbols = ['TTML', 'GESHIP', 'AEQUS']
times_of_interest = {
    'TTML': '09:35',
    'GESHIP': '09:50',
    'AEQUS': '10:25'
}

# Load the strategy code from strategies.json
strats = app.load_strategies_from_file()
strat = next(s for s in strats if '9:15 High Volume' in s['name'])
code_str = strat['code']

exec_env = {
    '__builtins__': __builtins__,
    'pd': pd,
    'np': np,
    'app': app,
    'get_market_cap_cr': app.get_market_cap_cr
}
exec(code_str, exec_env)
screen_func = exec_env['screen']

for sym in symbols:
    print(f"\n==================== {sym} ====================")
    df_symbol = app.get_ticker_data_duckdb(sym, timeframe='5m', start_date='2026-08-01', end_date='2026-09-28')
    print(f"Total 5m bars loaded: {len(df_symbol)}")
    today_bars = df_symbol[df_symbol.index.astype(str).str.startswith('2026-09-28')]
    print(f"Today 5m bars count: {len(today_bars)}")
    
    res = screen_func(df_symbol)
    out_df = res['df']
    today_out = out_df[out_df.index.astype(str).str.startswith('2026-09-28')]
    
    target_time = times_of_interest[sym]
    target_bar = today_out[today_out.index.astype(str).str.contains(target_time)]
    
    print(f"\n--- Checking bar around {target_time} for {sym} ---")
    if not target_bar.empty:
        b = target_bar.iloc[0]
        print(f"Time: {b.name}")
        print(f"Close: {b['close']}")
        print(f"Volume: {b['volume']}")
        print(f"Vol_Max_Prior_300_5min: {b.get('Vol_Max_Prior_300_5min')}")
        print(f"Cond_Volume_Breakout: {b.get('Cond_Volume_Breakout')}")
        print(f"Cond_Volume_Floor (>130k): {b.get('Cond_Volume_Floor')}")
        print(f"Daily_R2: {b.get('Daily_R2')}")
        print(f"Cond_Above_Daily_R2: {b.get('Cond_Above_Daily_R2')}")
        print(f"Weekly_R2: {b.get('Weekly_R2')}")
        print(f"Cond_Above_Weekly_R2: {b.get('Cond_Above_Weekly_R2')}")
        print(f"Scan_Pass (ALL CONDITIONS): {b.get('Scan_Pass')}")
    else:
        print(f"Bar {target_time} not found! Available today times:")
        print(today_out.index.astype(str).tolist()[:10])
    
    # Check if ANY bar today passed
    passed_today = today_out[today_out.get('Scan_Pass') == True]
    print(f"\nTotal bars passing ALL criteria today for {sym}: {len(passed_today)}")
    if not passed_today.empty:
        for idx, row in passed_today.iterrows():
            print(f"  MATCH: {idx} | Close={row['close']} | Vol={row['volume']}")

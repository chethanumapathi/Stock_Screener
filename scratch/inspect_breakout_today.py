import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
import pandas as pd
import numpy as np

strategies = app.load_strategies_from_file()
strat = [s for s in strategies if 'Strong buy' in s['name']][0]
code = strat['code']

exec_env = {
    '__builtins__': __builtins__,
    'pd': pd,
    'np': np,
    'get_market_cap_cr': app.get_market_cap_cr,
}
exec(code, exec_env)
screen_fn = exec_env['screen']

symbols = app.fetch_nifty50_symbols()
print(f"Testing {len(symbols)} Nifty 50 symbols for 2026-09-28...")

vol_breakouts = []

for sym in symbols:
    df = app.get_ticker_data_duckdb(sym, timeframe='5m', start_date='2026-08-01', end_date='2026-09-28')
    if df.empty or len(df) < 305:
        continue
    
    # Run screen
    res = screen_fn(df)
    out_df = res['df']
    
    # Filter for today's rows:
    today_mask = pd.to_datetime(out_df['Date']).dt.strftime('%Y-%m-%d') == '2026-09-28'
    today_df = out_df[today_mask]
    if today_df.empty:
        continue
    
    for idx, row in today_df.iterrows():
        t_str = str(row['Date'])
        c_brk = bool(row.get('Cond_Volume_Breakout', False))
        c_w2 = bool(row.get('Cond_Above_Weekly_R2', False))
        c_d2 = bool(row.get('Cond_Above_Daily_R2', False))
        c_flr = bool(row.get('Cond_Volume_Floor', False))
        pass_all = bool(row.get('Scan_Pass', False))
        
        vol_val = row.get('volume', row.get('Volume', 0))
        vol_max = row.get('Vol_Max_Prior_300_5min', 0)
        close_val = row.get('close', row.get('Close', 0))
        d_r2 = row.get('Daily_R2', 0)
        w_r2 = row.get('Weekly_R2', 0)
        
        if c_brk:
            vol_breakouts.append((sym, t_str, vol_val, vol_max, c_w2, c_d2, c_flr, close_val, d_r2, w_r2))
        if pass_all:
            print(f"MATCH: {sym} at {t_str} | Close: {close_val}, Vol: {vol_val}")

print(f"\nTotal 5m bars with Volume Breakout (Vol > 300-bar max): {len(vol_breakouts)}")
for item in vol_breakouts:
    print(f"  {item[0]} @ {item[1]}: Vol={int(item[2]):,} (300Max={int(item[3]):,}) | Close={item[7]:.2f}, D_R2={item[8]:.2f}({item[5]}), W_R2={item[9]:.2f}({item[4]}), Floor>130k={item[6]}")

import sys
sys.path.insert(0, r"c:\Stock_Screener")
import json
import os
import pandas as pd
import numpy as np
from app import get_ticker_data_duckdb, STRATEGIES_FILE, get_market_cap_cr

with open(STRATEGIES_FILE, 'r', encoding='utf-8') as f:
    strategies = json.load(f)

strat = next(s for s in strategies if '9:15 High Volume' in s['name'])
code_str = strat['code']

exec_env = {
    '__builtins__': __builtins__,
    'pd': pd,
    'np': np,
    'get_market_cap_cr': get_market_cap_cr,
}
exec(code_str, exec_env)
screen_fn = exec_env['screen']

stocks = ['TCI', 'SPARC', 'ARTEMISMED', 'LLOYDSENGG', 'LLOYDSENT', 'LCL']

print("================================================================================")
print("TEST 1: RUNNING STRATEGY AS-IS ON LATEST DATA (UP TO 2026-09-25)")
print("================================================================================")

for s in stocks:
    df = get_ticker_data_duckdb(s, timeframe='5m')
    df['symbol'] = s
    mcap = get_market_cap_cr(s, fetch_online=False)
    res = screen_fn(df)
    sig = res['signal']
    matches = df[sig == True]
    out_df = res['df']
    
    # Check 2026-09-25 matches
    matches_25 = matches[matches['Date'].astype(str).str.startswith('2026-09-25')]
    print(f"\nStock: {s:12} | Mcap: {mcap} Cr | 5m candles: {len(df)} | Matches on 2026-09-25: {len(matches_25)}")
    if len(matches_25) > 0:
        for idx, row in matches_25.iterrows():
            print(f"  --> MATCH: Time={row['Date']} Close={row['Close']} Volume={row['Volume']}")

    # Check candles on 2026-09-25 09:15 - 09:35
    df_25 = out_df[out_df['Date'].astype(str).str.startswith('2026-09-25')].head(6)
    for idx, row in df_25.iterrows():
        t = str(row['Date'])[11:16]
        c = row['close']
        v = row['volume']
        v_max_prior = row.get('Vol_Max_Prior_300_5min', np.nan)
        c_v_break = row.get('Cond_Volume_Breakout', False)
        c_v_floor = row.get('Cond_Volume_Floor', False)
        d_r2 = row.get('Daily_R2', np.nan)
        c_d_r2 = row.get('Cond_Above_Daily_R2', False)
        w_r2 = row.get('Weekly_R2', np.nan)
        c_w_r2 = row.get('Cond_Above_Weekly_R2', False)
        c_obv = row.get('Cond_OBV_15min_Breakout', False)
        passed = row.get('Scan_Pass', False)
        print(f"  [{t}] Px:{c:7.2f} (D_R2:{d_r2:7.2f}:{c_d_r2}, W_R2:{w_r2:7.2f}:{c_w_r2}) | Vol:{int(v):8d} (Prior300Max:{int(v_max_prior) if pd.notna(v_max_prior) else 'NaN'}:{c_v_break}, Floor>130k:{c_v_floor}) | OBV_15m:{c_obv} | PASS:{passed}")

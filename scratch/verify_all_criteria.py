import sys
sys.path.insert(0, r"c:\Stock_Screener")
import json
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
print("ANALYSIS ACROSS ALL DAYS (2026-09-21 TO 2026-09-25)")
print("================================================================================")

for s in stocks:
    df = get_ticker_data_duckdb(s, timeframe='5m')
    df['symbol'] = s
    mcap = get_market_cap_cr(s, fetch_online=False)
    
    # Run screen with actual mcap
    res = screen_fn(df)
    out_df = res['df']
    
    # Also if mcap <= 5000, let's run without mcap gate to see technical indicators!
    df_fake_mcap = df.copy()
    df_fake_mcap['market_cap_cr'] = 10000.0
    res_tech = screen_fn(df_fake_mcap)
    out_df_tech = res_tech['df']
    
    print(f"\n######################################################################")
    print(f"STOCK: {s} | Cached MCap: {mcap} Cr")
    print(f"######################################################################")
    
    # Check all triggers in the entire week 2026-09-21 to 2026-09-25
    week_mask = out_df['Date'].astype(str).str.startswith(('2026-09-21', '2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25'))
    week_df = out_df[week_mask]
    week_df_tech = out_df_tech[week_mask]
    
    matches_actual = week_df[week_df['Scan_Pass'] == True] if 'Scan_Pass' in week_df.columns else pd.DataFrame()
    matches_tech = week_df_tech[week_df_tech['Scan_Pass'] == True] if 'Scan_Pass' in week_df_tech.columns else pd.DataFrame()
    
    print(f"Triggers this week (Actual MCap): {len(matches_actual)}")
    for idx, r in matches_actual.iterrows():
        print(f"  --> ACTUAL TRIGGER: {r['Date']} | Close: {r['close']} | Vol: {r['volume']}")
        
    print(f"Triggers this week (Pure Technical - ignoring MCap gate): {len(matches_tech)}")
    for idx, r in matches_tech.iterrows():
        print(f"  --> TECH TRIGGER: {r['Date']} | Close: {r['close']} | Vol: {r['volume']}")
        
    # Check 09:15 candle for every day this week
    print(f"\n--- Checking 09:15 AM candle on each day (Pure Technical) ---")
    c_0915 = week_df_tech[week_df_tech['Date'].astype(str).str.endswith('09:15:00') | week_df_tech['Date'].astype(str).str.endswith('09:15')]
    for idx, r in c_0915.iterrows():
        d = str(r['Date'])[:10]
        c = r['close']
        v = r['volume']
        v_max = r['Vol_Max_Prior_300_5min']
        c_v_break = r['Cond_Volume_Breakout']
        c_v_floor = r['Cond_Volume_Floor']
        d_r2 = r['Daily_R2']
        c_d = r['Cond_Above_Daily_R2']
        w_r2 = r['Weekly_R2']
        c_w = r['Cond_Above_Weekly_R2']
        c_obv = r['Cond_OBV_15min_Breakout']
        passed = r['Scan_Pass']
        print(f"  Day {d} 09:15 | Px:{c:7.2f} (D_R2:{d_r2:7.2f}:{c_d}, W_R2:{w_r2:7.2f}:{c_w}) | Vol:{int(v):8d} (Prior300Max:{int(v_max) if pd.notna(v_max) else 'NaN'}:{c_v_break}, >130k:{c_v_floor}) | OBV:{c_obv} | PASS:{passed}")

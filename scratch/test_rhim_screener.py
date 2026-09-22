import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_kotak_history as fkh
import pandas as pd, json
import duckdb

config = fkh.load_env_config('kotak_credentials.env')
client_mgr = fkh.KotakClientManager(config)
scrip_resolver = fkh.ScripResolver(client_mgr)
tok = scrip_resolver.get_token('RHIM')
res = client_mgr.fetch_historical_candles(tok, '1min', '2026-09-21', '2026-09-23')
candles = res.get('data', {}).get('candles', [])

# Load existing parquet
df_hist = pd.read_parquet(r'C:\Zerodha Historical Data\data\minute\RHIM.parquet')
print('Hist rows:', len(df_hist), 'max:', df_hist['date'].max())

# New candles
new_rows = []
for c in candles:
    dt = pd.to_datetime(c[0]).tz_localize(None) if hasattr(pd.to_datetime(c[0]), 'tz_localize') else pd.to_datetime(c[0])
    new_rows.append({
        'date': dt,
        'open': float(c[1]),
        'high': float(c[2]),
        'low': float(c[3]),
        'close': float(c[4]),
        'volume': float(c[5])
    })
df_new = pd.DataFrame(new_rows)
df_new['date'] = pd.to_datetime(df_new['date']).dt.tz_localize(None)
df_hist['date'] = pd.to_datetime(df_hist['date']).dt.tz_localize(None)

df_all = pd.concat([df_hist, df_new]).drop_duplicates(subset=['date']).sort_values('date').reset_index(drop=True)
print('Combined rows:', len(df_all), 'max:', df_all['date'].max())

# Resample to 5m
con = duckdb.connect()
con.register('df_all', df_all)
df_5m = con.execute('''
    SELECT 
        time_bucket(INTERVAL '5 Minutes', date::TIMESTAMP) as date,
        FIRST(open) as open,
        MAX(high) as high,
        MIN(low) as low,
        LAST(close) as close,
        SUM(volume) as volume,
        FIRST(open) as Open,
        MAX(high) as High,
        MIN(low) as Low,
        LAST(close) as Close,
        SUM(volume) as Volume,
        'RHIM' as Symbol,
        5500.0 as Market_Cap_Cr
    FROM df_all
    GROUP BY 1
    ORDER BY 1
''').df()
df_5m['Date'] = df_5m['date'].astype(str)
df_5m.set_index('date', inplace=True)
print('5m shape:', df_5m.shape, 'last row:', df_5m.index[-1])

# Run strategy
with open('data/strategies.json', 'r', encoding='utf-8') as f:
    strategies = json.load(f)
code = [s['code'] for s in strategies if 'Strong buy' in s['name']][0]
env = {}
exec(code, env)
func = env['screen']

res = func(df_5m)
sig = res['signal']
matches_today = sig[sig.index >= '2026-09-22']
print('Today matches count:', len(matches_today[matches_today == True]))
print('All matches today:\n', matches_today[matches_today == True])

# Let's inspect df output for today 09:15
out_df = res['df']
print('\nCondition values around 2026-09-22 09:15:\n', out_df[out_df.index >= '2026-09-22 09:15'].head(5)[[
    'close', 'volume', 'Vol_Max_Prior_300_5min', 'Cond_Volume_Breakout',
    'Daily_R2', 'Cond_Above_Daily_R2', 'Weekly_R2', 'Cond_Above_Weekly_R2',
    'Cond_Volume_Floor', 'Cond_OBV_15min_Breakout', 'Scan_Pass'
]])

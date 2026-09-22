import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_kotak_history as fkh
import pandas as pd, json, duckdb

config = fkh.load_env_config('kotak_credentials.env')
client_mgr = fkh.KotakClientManager(config)
scrip_resolver = fkh.ScripResolver(client_mgr)

stocks = ['RHIM', 'TRANSRAILL', 'JAINREC', 'OPTIEMUS', 'ENGINERSIN', 'SUNTV', 'GABRIEL']

with open('data/strategies.json', 'r', encoding='utf-8') as f:
    strategies = json.load(f)
code = [s['code'] for s in strategies if 'Strong buy' in s['name']][0]
env = {}
exec(code, env)
func = env['screen']

con = duckdb.connect()

for sym in stocks:
    tok = scrip_resolver.get_token(sym)
    res = client_mgr.fetch_historical_candles(tok, '1min', '2026-09-21', '2026-09-23')
    candles = res.get('data', {}).get('candles', []) if isinstance(res, dict) else []

    p_file = rf'C:\Zerodha Historical Data\data\minute\{sym}.parquet'
    df_hist = pd.read_parquet(p_file)
    df_hist['date'] = pd.to_datetime(df_hist['date']).dt.tz_localize(None)

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
    if not df_new.empty:
        df_new['date'] = pd.to_datetime(df_new['date']).dt.tz_localize(None)
        df_all = pd.concat([df_hist, df_new]).drop_duplicates(subset=['date']).sort_values('date').reset_index(drop=True)
    else:
        df_all = df_hist

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
            ? as Symbol,
            6000.0 as Market_Cap_Cr
        FROM df_all
        GROUP BY 1
        ORDER BY 1
    ''', [sym]).df()
    df_5m['Date'] = df_5m['date'].astype(str)
    df_5m.set_index('date', inplace=True)

    res = func(df_5m)
    sig = res['signal']
    matches_today = sig[(sig.index >= '2026-09-22') & (sig == True)]
    print(f'[{sym}] Matches on 2026-09-22: {len(matches_today)}')
    for t in matches_today.index:
        print(f'   -> {t}')

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
import pandas as pd

with open('data/strategies.json', 'r', encoding='utf-8') as f:
    strategies = app.json.load(f)
code_str = [s['code'] for s in strategies if 'Strong buy' in s['name']][0]

exec_env = {
    'pd': pd,
    'np': app.np,
    'datetime': app.datetime,
    'timedelta': app.timedelta,
    'get_market_cap_cr': app.get_market_cap_cr,
    'get_stock_fundamentals': app.get_stock_fundamentals,
}
exec(code_str, exec_env)
screen_func = exec_env['screen']

for sym in ['RHIM', 'TRANSRAILL', 'OPTIEMUS']:
    df_full = app.get_ticker_data_duckdb(sym, timeframe='5m', start_date=None, end_date='2026-09-22')
    res_full = screen_func(df_full)
    sig_full = res_full['signal']

    start_60d = pd.to_datetime('2026-09-22') - pd.Timedelta(days=60)
    df_60d = app.get_ticker_data_duckdb(sym, timeframe='5m', start_date=start_60d, end_date='2026-09-22')
    res_60d = screen_func(df_60d)
    sig_60d = res_60d['signal']

    m_full = list(sig_full[(sig_full.index >= '2026-09-22') & (sig_full == True)].index.astype(str))
    m_60d = list(sig_60d[(sig_60d.index >= '2026-09-22') & (sig_60d == True)].index.astype(str))
    print(f"[{sym}] Full matches:", m_full)
    print(f"[{sym}] 60d matches: ", m_60d)
    assert m_full == m_60d, f"Mismatch for {sym}!"
print("ALL SIGNALS MATCH IDENTICALLY!")

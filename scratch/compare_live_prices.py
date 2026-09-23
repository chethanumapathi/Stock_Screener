import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch_kotak_history as fkh
import yfinance as yf

config = fkh.load_env_config('kotak_credentials.env')
cm = fkh.KotakClientManager(config)
sr = fkh.ScripResolver(cm)

for sym in ['RELIANCE', 'ELECON']:
    tok = sr.get_token(sym)
    q = cm.client.quotes(instrument_tokens=[{'instrument_token': tok.split('|')[1], 'exchange_segment': 'nse_cm'}], quote_type='ltp')
    print(f'Kotak Quote for {sym}: {q}')
    
    res = cm.fetch_historical_candles(tok, '1min', '2026-09-23', '2026-09-23')
    c = res.get('data', {}).get('candles', []) if res else []
    if c:
        print(f'Kotak Latest 1m candle for {sym}: {c[-1]}')
    
    try:
        t = yf.Ticker(f'{sym}.NS')
        h = t.history(period='1d', interval='1m')
        if not h.empty:
            print(f'YFinance Latest 1m for {sym}: Close={h["Close"].iloc[-1]}, High={h["High"].iloc[-1]}, Low={h["Low"].iloc[-1]} at {h.index[-1]}')
        else:
            print(f'YFinance empty for {sym}')
    except Exception as e:
        print(f'YFinance error for {sym}: {e}')

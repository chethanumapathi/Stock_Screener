import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
import datetime

client = app.test_client()

for sym in ['TCS', 'INFY', 'ELECON', 'SBIN', 'SUNTECK', 'TATAMOTORS']:
    resp = client.get(f'/api/orderflow/chart-data?symbol={sym}&timeframe=5m')
    d = resp.get_json()
    if d and d.get('status') == 'ok':
        data = d.get('data', {})
        ohlc = data.get('ohlc', [])
        print(f'{sym} 5m: {len(ohlc)} candles')
        if ohlc:
            t0 = datetime.datetime.fromtimestamp(ohlc[0]['time'])
            t1 = datetime.datetime.fromtimestamp(ohlc[-1]['time'])
            print(f'   Range: {t0} to {t1}')
    else:
        print(f'{sym}: error or empty: {d}')

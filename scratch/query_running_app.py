import urllib.request
import json
import datetime

for sym in ['RELIANCE', 'ELECON', 'TCS', 'INFY', 'SUNTECK']:
    for tf in ['1m', '5m', '15m']:
        url = f'http://127.0.0.1:8000/api/orderflow/chart-data?symbol={sym}&timeframe={tf}'
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                ohlc = data.get('data', {}).get('ohlc', [])
                print(f'{sym} {tf}: count={len(ohlc)}')
                if ohlc:
                    t0 = datetime.datetime.fromtimestamp(ohlc[0]['time'])
                    t1 = datetime.datetime.fromtimestamp(ohlc[-1]['time'])
                    print(f'   first: {t0} (O={ohlc[0]["open"]}) | last: {t1} (C={ohlc[-1]["close"]})')
        except Exception as e:
            print(f'{sym} {tf}: Error {e}')

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_kotak_history as fkh
from orderflow_engine import OrderFlowDatabase, DeltaCandleAggregator
from datetime import datetime

config = fkh.load_env_config('kotak_credentials.env')
mgr = fkh.KotakClientManager(config)
resolver = fkh.ScripResolver(mgr)
token = resolver.get_token('RELIANCE')
today_str = datetime.now().strftime('%Y-%m-%d')
res = mgr.fetch_historical_candles(token, '1min', today_str, today_str)
candles_1m = res['data']['candles']

db = OrderFlowDatabase(':memory:')
agg = DeltaCandleAggregator('RELIANCE', db)

# Populate 1m candles
bars_5m = {}
cum_delta = 0

for c in candles_1m:
    dt = datetime.fromisoformat(c[0])
    epoch = int(dt.timestamp())
    o, h, l, cl, v = float(c[1]), float(c[2]), float(c[3]), float(c[4]), int(c[5])
    rng = h - l
    ratio = (cl - l) / rng if rng > 0 else 0.5
    buy_v = int(v * ratio)
    sell_v = v - buy_v
    bar_delta = buy_v - sell_v
    cum_delta += bar_delta
    
    candle_1m = {
        'symbol': 'RELIANCE',
        'timeframe': '1m',
        'time': epoch,
        'datetime_str': dt.strftime('%Y-%m-%d %H:%M:%S'),
        'open': o,
        'high': h,
        'low': l,
        'close': cl,
        'volume': v,
        'buy_volume': buy_v,
        'sell_volume': sell_v,
        'delta': bar_delta,
        'cum_delta': cum_delta,
        'trades_count': max(1, int(v / 50))
    }
    agg.candles_history['1m'].append(candle_1m)
    
    # 5m bucket
    b5_time = (epoch // 300) * 300
    if b5_time not in bars_5m:
        bars_5m[b5_time] = {
            'symbol': 'RELIANCE',
            'timeframe': '5m',
            'time': b5_time,
            'datetime_str': datetime.fromtimestamp(b5_time).strftime('%Y-%m-%d %H:%M:%S'),
            'open': o,
            'high': h,
            'low': l,
            'close': cl,
            'volume': v,
            'buy_volume': buy_v,
            'sell_volume': sell_v,
            'delta': bar_delta,
            'cum_delta': cum_delta,
            'trades_count': candle_1m['trades_count']
        }
    else:
        b = bars_5m[b5_time]
        b['high'] = max(b['high'], h)
        b['low'] = min(b['low'], l)
        b['close'] = cl
        b['volume'] += v
        b['buy_volume'] += buy_v
        b['sell_volume'] += sell_v
        b['delta'] += bar_delta
        b['cum_delta'] = cum_delta
        b['trades_count'] += candle_1m['trades_count']

agg.candles_history['5m'] = sorted(bars_5m.values(), key=lambda x: x['time'])

series = agg.get_chart_series('5m')
for o, v, d in zip(series['ohlc'], series['volume'], series['delta']):
    dt_str = datetime.fromtimestamp(o['time']).strftime('%H:%M')
    if dt_str in ['13:10', '13:15', '13:20', '13:25', '13:30']:
        print(f"{dt_str} | OHLC: {o['open']}/{o['high']}/{o['low']}/{o['close']} | Vol: {v['value']} | Delta: {d['value']}")

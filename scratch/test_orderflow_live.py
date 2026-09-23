import sys
sys.path.insert(0, '.')
import time
from orderflow_engine import OrderFlowEngine
import fetch_kotak_history as fkh

engine = OrderFlowEngine.get_instance()
time.sleep(1)

for sym in ['ELECON', 'RELIANCE']:
    engine.subscribe_symbol(sym)
    agg = engine._get_or_create_aggregator(sym)
    print(f"=== {sym} ===")
    print(f"Aggregator Last Price: {agg.last_price}")
    print(f"Day Open: {agg.day_open}, High: {agg.day_high}, Low: {agg.day_low}, PrevClose: {agg.prev_close}")
    s = agg.get_chart_series('5m')
    print(f"Latest stats in chart series: {s['latest']}")
    print(f"Total 5m bars: {len(s['ohlc'])}")
    if s['ohlc']:
        print(f"Last 5m candle: {s['ohlc'][-1]}")
    
    # Compare with direct Kotak quote
    tok = engine.scrip_resolver.get_token(sym).split("|")[1]
    q = engine.kotak_client.quotes(instrument_tokens=[{"instrument_token": tok, "exchange_segment": "nse_cm"}])
    if q and len(q) > 0:
        direct_ltp = float(q[0].get('ltp', 0))
        print(f"Direct Kotak Exchange Quote LTP: {direct_ltp}")
        diff = abs(agg.last_price - direct_ltp)
        print(f"Price Difference: {diff:.4f} (Match: {diff == 0})")
    print()

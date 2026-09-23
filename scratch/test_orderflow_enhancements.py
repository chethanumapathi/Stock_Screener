import os
import sys
import datetime

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orderflow_engine import OrderFlowEngine

# Temporary clean instance
engine = OrderFlowEngine.get_instance()

test_symbols = ['ELECON', 'TCS', 'INFY', 'SUNTECK', 'RELIANCE']
print("=" * 70)
print("TESTING ORDERFLOW ENHANCEMENTS")
print("=" * 70)

for sym in test_symbols:
    agg = engine._get_or_create_aggregator(sym)
    # Force re-seed
    agg.is_seeded = False
    agg.candles_history['1m'] = []
    engine._seed_baseline_if_empty(sym)

    print(f"\n--- Symbol: {sym} ---")
    for tf in ['1m', '3m', '5m', '15m', '1h']:
        data = agg.get_chart_series(timeframe=tf)
        ohlc = data.get('ohlc', [])
        vol = data.get('volume', [])
        delta = data.get('delta', [])
        cvd = data.get('cvd', [])

        times = [b['time'] for b in ohlc]
        has_dups = any(times[i] <= times[i-1] for i in range(1, len(times)))

        if ohlc:
            t0 = datetime.datetime.fromtimestamp(ohlc[0]['time'])
            t1 = datetime.datetime.fromtimestamp(ohlc[-1]['time'])
            print(f"  {tf:4s}: count={len(ohlc):3d} | Range: {t0} to {t1} | Strictly Ascending: {not has_dups}")
        else:
            print(f"  {tf:4s}: EMPTY (count=0) | Strictly Ascending: N/A")

        assert not has_dups, f"Duplicate timestamps found in {sym} {tf}!"

print("\nALL SYMBOLS AND TIMEFRAMES PASSED STRICT MONOTONIC ASCENDING CHECKS!")

import sys
sys.path.insert(0, '.')
import requests
import json
import traceback
import app
import backtest_diagnostics as bd

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    strats = json.load(f)
target = next(s for s in strats if 'Weekly Yearly-R1' in s['name'])
strat_code = target['code']

resp = requests.post("http://127.0.0.1:8000/api/backtest", json={
    "code": strat_code,
    "segment": "nifty50",
    "timeframe": "1d",
    "start_date": "2023-01-01",
    "end_date": "2026-09-20",
    "capital_per_trade": 100000.0,
    "slippage_pct": 0.5,
    "include_brokerage": True,
    "include_taxes": True,
    "brokerage_per_order": 20.0,
    "min_market_cap_cr": 0.0
}, timeout=60)

bt_data = resp.json()
trades = bt_data.get('trades', [])
print(f"Got {len(trades)} trades")

# Now let's call compute_backtest_analytics directly
try:
    res = app.compute_backtest_analytics(
        trades,
        slippage_pct=0.5,
        include_brokerage=True,
        include_taxes=True,
        brokerage_per_order=20.0,
        capital_per_trade=100000.0,
        compute_diagnostics=True
    )
    print("Diagnostics result keys:", list(res.get('diagnostics', {}).keys()))
except Exception as e:
    traceback.print_exc()

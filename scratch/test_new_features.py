import urllib.request
import json
import time

print("1. Testing /api/status...")
with urllib.request.urlopen('http://localhost:8000/api/status') as r:
    status_data = json.loads(r.read())
latest_date = status_data.get('latest_date')
print(f"Status latest_date: {latest_date}")
assert latest_date == '2026-09-18', f"Expected 2026-09-18, got {latest_date}"

print("\n2. Testing /api/dates...")
with urllib.request.urlopen('http://localhost:8000/api/dates') as r:
    dates_data = json.loads(r.read())
dates = dates_data.get('dates', [])
print(f"Dates total: {len(dates)}, top 5: {dates[:5]}")
assert dates[0] == '2026-09-18', f"Expected top date 2026-09-18, got {dates[0]}"

print("\n3. Testing Backtest on Weekly timeframe (1w)...")
t0 = time.time()
req_body = json.dumps({
    'code': "def screen(df):\n    df['ema20'] = df['Close'].ewm(span=20, adjust=False).mean()\n    signal = df['Close'] > df['ema20']\n    return {'long_entry': signal, 'tp_pct': 0.10, 'sl_pct': 0.05}",
    'segment': 'nifty50',
    'timeframe': '1w',
    'capital_per_trade': 100000,
    'end_date': '2026-09-18'
}).encode('utf-8')
req = urllib.request.Request('http://localhost:8000/api/backtest', data=req_body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req) as r:
    bt_res = json.loads(r.read())
print(f"Weekly backtest status: {bt_res.get('status')} | Trades: {bt_res.get('total_trades')} | Net PnL: Rs {bt_res.get('net_pnl')} | Duration: {bt_res.get('duration_seconds')}s (Network: {time.time()-t0:.2f}s)")
assert bt_res.get('status') == 'success', f"Weekly backtest failed: {bt_res.get('message')}"
assert bt_res.get('total_trades', 0) > 0, 'Weekly backtest produced 0 trades'

print("\n4. Testing Backtest on Monthly timeframe (1mo)...")
t0 = time.time()
req_body_m = json.dumps({
    'code': "def screen(df):\n    signal = df['Close'] > df['Open']\n    return {'long_entry': signal, 'tp_pct': 0.15, 'sl_pct': 0.08}",
    'segment': 'nifty50',
    'timeframe': '1mo',
    'capital_per_trade': 100000,
    'end_date': '2026-09-18'
}).encode('utf-8')
req_m = urllib.request.Request('http://localhost:8000/api/backtest', data=req_body_m, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req_m) as r:
    bt_res_m = json.loads(r.read())
print(f"Monthly backtest status: {bt_res_m.get('status')} | Trades: {bt_res_m.get('total_trades')} | Duration: {bt_res_m.get('duration_seconds')}s (Network: {time.time()-t0:.2f}s)")
assert bt_res_m.get('status') == 'success', f"Monthly backtest failed: {bt_res_m.get('message')}"
assert bt_res_m.get('total_trades', 0) > 0, 'Monthly backtest produced 0 trades'

print("\n>>> ALL 4 BACKEND VERIFICATION CHECKS PASSED PERFECTLY! <<<")

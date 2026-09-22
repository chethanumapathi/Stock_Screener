import requests, json, time

with open('data/strategies.json', 'r', encoding='utf-8') as f:
    strategies = json.load(f)
code = [s['code'] for s in strategies if 'Strong buy' in s['name']][0]

payload = {
    'code': code,
    'segment': 'nifty500',
    'timeframe': '5m',
    'start_date': '2026-09-22',
    'end_date': '2026-09-22',
    'min_market_cap_cr': 5000.0
}

t0 = time.time()
print("Sending /api/screen request for Nifty 500 (500 stocks)...")
res = requests.post('http://localhost:8000/api/screen', json=payload)
elapsed = time.time() - t0
data = res.json()
print(f"Completed in {elapsed:.2f}s!")
print('Status:', data.get('status'))
print('Total matches:', data.get('total_matches'))
matches = data.get('flat_matches', [])
print('Matches count:', len(matches))
for m in matches[:10]:
    print(m['Date'], m['Symbol'], 'Close:', m['Close'], 'Vol:', m['Volume'])

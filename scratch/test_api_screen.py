import requests, json

with open('data/strategies.json', 'r', encoding='utf-8') as f:
    strategies = json.load(f)
code = [s['code'] for s in strategies if 'Strong buy' in s['name']][0]

payload = {
    'code': code,
    'segment': 'watchlist',
    'timeframe': '5m',
    'watchlist': ['RHIM', 'TRANSRAILL', 'JAINREC', 'OPTIEMUS', 'ENGINERSIN', 'SUNTV', 'GABRIEL'],
    'start_date': '2026-09-22',
    'end_date': '2026-09-22',
    'min_market_cap_cr': 5000.0
}

res = requests.post('http://localhost:8000/api/screen', json=payload)
data = res.json()
print('Status:', data.get('status'))
print('Total matches:', data.get('total_matches'))
matches = data.get('flat_matches', [])
print('Matches count:', len(matches))
for m in matches:
    print(m['Date'], m['Symbol'], 'Close:', m['Close'], 'Vol:', m['Volume'])

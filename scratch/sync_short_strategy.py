import json

TARGET_NAME = '5-Min Daily R3 + RSI>85 Short (1m VWAP Breakdown | TP 2% | SL Day High | Daily 260 EMA)'
MATCH_NAMES = [
    TARGET_NAME,
    '5-Min Daily R3 + RSI>85 Short (TP 5m 50 EMA | SL 2% Above High | Daily 260 EMA)',
    '5-Min Daily R3 + RSI>85 Short (TP 5m 50 EMA | SL 2% Above High)',
    '5-Min Daily R3 + RSI>85 Breakout (TP 2% | SL 5m 50 EMA Low)'
]

with open('strategies/five_min_daily_r3_rsi85_ema50_sl.py', 'r', encoding='utf-8') as f:
    CODE = f.read()

for json_file in ['data/backtest_strategies.json', 'data/strategies.json']:
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    found = False
    for item in data:
        if item.get('name') in MATCH_NAMES or ('Daily R3' in item.get('name', '') and 'RSI>85' in item.get('name', '')):
            item['name'] = TARGET_NAME
            item['code'] = CODE
            found = True
            break
    if not found:
        data.append({'name': TARGET_NAME, 'code': CODE})
        
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f'Synced into {json_file} as "{TARGET_NAME}" (Total: {len(data)})')

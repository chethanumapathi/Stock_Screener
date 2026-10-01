import json

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt = json.load(f)

for idx, s in enumerate(bt):
    print('='*60)
    print(f"STRATEGY {idx+1}: {s['name']}")
    lines = s['code'].split('\n')
    for line in lines:
        if any(k in line for k in ['exit_reason', 'is_open', 'close_trade', 'OPEN_TIMEOUT', 'End of Data', 'Still Running', 'exit_date']):
            print('  ', line.strip())

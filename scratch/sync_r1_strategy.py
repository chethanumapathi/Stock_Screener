import json

NAME = "Weekly Yearly-R1 Breakout Strategy (RSI > 80 + 400% TP & 30 EMA Trailing Exit)"
with open('strategies/weekly_yearly_r1_breakout.py', 'r', encoding='utf-8') as f:
    code = f.read()

path = 'data/backtest_strategies.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

updated = False
for item in data:
    if item.get('name') == NAME:
        item['code'] = code
        updated = True
        break

if updated:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f'Successfully updated "{NAME}" in {path}!')
else:
    print(f'Error: "{NAME}" not found in {path}')

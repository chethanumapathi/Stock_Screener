import json

with open('strategies/weekly_yearly_r1_breakout.py', 'r', encoding='utf-8') as f:
    strategy_code = f.read()

target_name = "Weekly Yearly-R1 Breakout Strategy (RSI > 80 + Next Bar Breakout + 100% TP & 30 EMA Trailing Exit)"

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    strategies = json.load(f)

found = False
for s in strategies:
    if s.get('name') == target_name:
        s['code'] = strategy_code
        found = True
        break

if not found:
    strategies.append({
        'name': target_name,
        'code': strategy_code
    })

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(strategies, f, indent=4)

print(f'Successfully updated "{target_name}" in data/backtest_strategies.json!')

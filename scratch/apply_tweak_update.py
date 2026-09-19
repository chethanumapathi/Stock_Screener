import json
from scratch.test_validator_run import STRATEGY_CODE

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    strategies = json.load(f)

found = False
for s in strategies:
    if s.get('name') == 'Weekly Yearly-R1 Breakout Strategy':
        s['code'] = STRATEGY_CODE
        found = True
        break

if not found:
    strategies.append({
        'name': 'Weekly Yearly-R1 Breakout Strategy',
        'code': STRATEGY_CODE
    })

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(strategies, f, indent=4)

print("Successfully updated Weekly Yearly-R1 Breakout Strategy in data/backtest_strategies.json!")

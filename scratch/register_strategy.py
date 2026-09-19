import json

with open('strategies/daily_rsi85_weekly_ema_stack.py', 'r', encoding='utf-8') as f:
    strategy_code = f.read()

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    strategies = json.load(f)

strategy_name = "Daily RSI 85 + Weekly 10/30/40 EMA Stack Strategy"
found = False
for s in strategies:
    if s.get('name') == strategy_name:
        s['code'] = strategy_code
        found = True
        break

if not found:
    strategies.append({
        'name': strategy_name,
        'code': strategy_code
    })

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(strategies, f, indent=4)

print(f'Successfully registered "{strategy_name}" into data/backtest_strategies.json!')

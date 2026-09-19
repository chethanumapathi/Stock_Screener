import json

with open('strategies/daily_rsi85_weekly_ema_stack.py', 'r', encoding='utf-8') as f:
    strategy_code = f.read()

strategy_name = "Daily RSI 85 + Weekly 10/30/40 EMA Stack Strategy"

# 1. Update data/backtest_strategies.json
with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_strategies = json.load(f)

found_bt = False
for s in bt_strategies:
    if s.get('name') == strategy_name:
        s['code'] = strategy_code
        found_bt = True
        break

if not found_bt:
    bt_strategies.append({'name': strategy_name, 'code': strategy_code})

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(bt_strategies, f, indent=4)

print("Updated data/backtest_strategies.json")

# 2. Update data/strategies.json
with open('data/strategies.json', 'r', encoding='utf-8') as f:
    sc_strategies = json.load(f)

found_sc = False
for s in sc_strategies:
    if s.get('name') == strategy_name:
        s['code'] = strategy_code
        found_sc = True
        break

if not found_sc:
    sc_strategies.append({'name': strategy_name, 'code': strategy_code})

with open('data/strategies.json', 'w', encoding='utf-8') as f:
    json.dump(sc_strategies, f, indent=4)

print("Updated data/strategies.json")

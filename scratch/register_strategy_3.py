import json

STRATEGY_NAME = "15-Min Weekly R3 Trigger -> Weekly R2 + RSI>80 Breakout (TP 3% | VWAP SL)"
STRATEGY_PATH = "strategies/fifteen_min_weekly_r3_r2_rsi80.py"

with open(STRATEGY_PATH, 'r', encoding='utf-8') as f:
    strategy_code = f.read()

# 1. Update data/backtest_strategies.json
with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_strategies = json.load(f)

bt_found = False
for s in bt_strategies:
    if s.get('name') == STRATEGY_NAME:
        s['code'] = strategy_code
        bt_found = True
        break

if not bt_found:
    bt_strategies.append({
        'name': STRATEGY_NAME,
        'code': strategy_code
    })

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(bt_strategies, f, indent=4)
print(f"Successfully registered '{STRATEGY_NAME}' into data/backtest_strategies.json")

# 2. Update data/strategies.json
with open('data/strategies.json', 'r', encoding='utf-8') as f:
    screener_strategies = json.load(f)

sc_found = False
for s in screener_strategies:
    if s.get('name') == STRATEGY_NAME:
        s['code'] = strategy_code
        sc_found = True
        break

if not sc_found:
    screener_strategies.append({
        'name': STRATEGY_NAME,
        'code': strategy_code
    })

with open('data/strategies.json', 'w', encoding='utf-8') as f:
    json.dump(screener_strategies, f, indent=4)
print(f"Successfully registered '{STRATEGY_NAME}' into data/strategies.json")

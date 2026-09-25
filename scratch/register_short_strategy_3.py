import json

NEW_NAME = "1-Hour Weekly R3 Trigger -> 5-Min Weekly R2 + RSI>85 Short (TP VWAP | SL 3%)"
OLD_NAMES = [
    "1-Hour Weekly R3 Trigger -> 5-Min Weekly R2 + RSI>85 Breakout (TP 3% | Dual VWAP & R2 SL)",
    "15-Min Weekly R3 Trigger -> Weekly R2 + RSI>80 Breakout (TP 3% | VWAP SL)"
]
STRATEGY_PATH = "strategies/fifteen_min_weekly_r3_r2_rsi80.py"

with open(STRATEGY_PATH, 'r', encoding='utf-8') as f:
    strategy_code = f.read()

# 1. Update data/backtest_strategies.json
with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_strategies = json.load(f)

updated_bt = False
for s in bt_strategies:
    if s.get('name') in OLD_NAMES or s.get('name') == NEW_NAME:
        s['name'] = NEW_NAME
        s['code'] = strategy_code
        updated_bt = True
        break

if not updated_bt:
    bt_strategies.append({
        'name': NEW_NAME,
        'code': strategy_code
    })

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(bt_strategies, f, indent=4)
print(f"Successfully registered '{NEW_NAME}' into data/backtest_strategies.json")

# 2. Update data/strategies.json
with open('data/strategies.json', 'r', encoding='utf-8') as f:
    screener_strategies = json.load(f)

updated_sc = False
for s in screener_strategies:
    if s.get('name') in OLD_NAMES or s.get('name') == NEW_NAME:
        s['name'] = NEW_NAME
        s['code'] = strategy_code
        updated_sc = True
        break

if not updated_sc:
    screener_strategies.append({
        'name': NEW_NAME,
        'code': strategy_code
    })

with open('data/strategies.json', 'w', encoding='utf-8') as f:
    json.dump(screener_strategies, f, indent=4)
print(f"Successfully registered '{NEW_NAME}' into data/strategies.json")

import json

STRATEGY_PATH = "strategies/intraday_rsi_volume_vwap_r2.py"
with open(STRATEGY_PATH, 'r', encoding='utf-8') as f:
    strategy_code = f.read()

TARGET_NAME = "15-Min Intraday Dual RSI (80/85) + 2M Volume Peak + Daily R2 (Short | TP VWAP | SL 2%)"
OLD_NAME = "15-Min Intraday Dual RSI (80/85) + 2M Volume Peak + Daily R2 (TP 3% | VWAP SL)"

# 1. Update data/backtest_strategies.json
with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_strategies = json.load(f)

updated_bt = False
for s in bt_strategies:
    if s.get('name') in (TARGET_NAME, OLD_NAME):
        s['name'] = TARGET_NAME
        s['code'] = strategy_code
        updated_bt = True
        break

if not updated_bt:
    bt_strategies.append({'name': TARGET_NAME, 'code': strategy_code})

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(bt_strategies, f, indent=4)
print(f"Updated '{TARGET_NAME}' in data/backtest_strategies.json")

# 2. Update data/strategies.json
with open('data/strategies.json', 'r', encoding='utf-8') as f:
    screener_strategies = json.load(f)

updated_sc = False
for s in screener_strategies:
    if s.get('name') in (TARGET_NAME, OLD_NAME):
        s['name'] = TARGET_NAME
        s['code'] = strategy_code
        updated_sc = True
        break

if not updated_sc:
    screener_strategies.append({'name': TARGET_NAME, 'code': strategy_code})

with open('data/strategies.json', 'w', encoding='utf-8') as f:
    json.dump(screener_strategies, f, indent=4)
print(f"Updated '{TARGET_NAME}' in data/strategies.json")

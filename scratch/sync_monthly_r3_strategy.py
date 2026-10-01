import json

with open('strategies/daily_monthly_r3_yearly_r2_breakout.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Update backtest_strategies.json
with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_data = json.load(f)

updated_bt = False
for s in bt_data:
    if 'Daily Monthly-R3 Breakout above Yearly-R2' in s.get('name', ''):
        s['code'] = code
        print('Updated in backtest_strategies.json:', s['name'])
        updated_bt = True

if updated_bt:
    with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
        json.dump(bt_data, f, indent=4)

# Update strategies.json
with open('data/strategies.json', 'r', encoding='utf-8') as f:
    st_data = json.load(f)

updated_st = False
for s in st_data:
    if 'Daily Monthly-R3 Breakout above Yearly-R2' in s.get('name', ''):
        s['code'] = code
        print('Updated in strategies.json:', s['name'])
        updated_st = True

if updated_st:
    with open('data/strategies.json', 'w', encoding='utf-8') as f:
        json.dump(st_data, f, indent=4)

print('Sync complete.')

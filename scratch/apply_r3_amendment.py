import json

with open('scratch/strong_buy_scan_amended.py', 'r', encoding='utf-8') as f:
    amended_code = f.read()

target_name = "Strong Buy Scan (5-min Volume Breakout + Weekly/Daily R2 + MCap + 15-min OBV)"

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    strategies = json.load(f)

updated = False
for s in strategies:
    if s.get('name') == target_name:
        s['code'] = amended_code
        updated = True
        print(f"Found and updated '{target_name}' in data/backtest_strategies.json")
        break

if not updated:
    print(f"ERROR: Strategy '{target_name}' not found!")
    exit(1)

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(strategies, f, indent=4)

print("Successfully written updated data/backtest_strategies.json!")

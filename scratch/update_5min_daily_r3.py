import json
import re

for path in ['data/backtest_strategies.json', 'data/strategies.json']:
    with open(path, 'r', encoding='utf-8') as f:
        strats = json.load(f)
    for s in strats:
        if '5-Min Daily R3' in s.get('name', ''):
            old_str = '"exit_date": dates_1m[-1],\n            "exit_price": round(float(close_1m[-1]), 2),\n            "exit_reason": "End of Data",'
            new_str = '"exit_date": "-",\n            "exit_price": round(float(close_1m[-1]), 2),\n            "exit_reason": "Still Running",'
            if old_str in s['code']:
                s['code'] = s['code'].replace(old_str, new_str)
                print(f"Updated 5-Min Daily R3 in {path}")
            else:
                # Try generic replacement
                s['code'] = re.sub(
                    r'"exit_date":\s*dates_1m\[-1\],\s*"exit_price":\s*round\(float\(close_1m\[-1\]\),\s*2\),\s*"exit_reason":\s*"End of Data",',
                    r'"exit_date": "-",\n            "exit_price": round(float(close_1m[-1]), 2),\n            "exit_reason": "Still Running",',
                    s['code']
                )
                print(f"Regex updated 5-Min Daily R3 in {path}")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(strats, f, indent=4)

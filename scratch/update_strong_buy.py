import json

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    strats = json.load(f)

s = strats[0]
old_line = "'exit_date': str(date_strs[i]),"
new_line = "'exit_date': '-' if is_open else str(date_strs[i]),"
s['code'] = s['code'].replace(old_line, new_line)

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(strats, f, indent=4)

print("Updated Strong Buy Scan exit_date successfully!")

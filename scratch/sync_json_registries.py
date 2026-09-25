import json

with open('strategies/fifteen_min_weekly_r3_r2_rsi80.py', 'r', encoding='utf-8') as f:
    strat_code = f.read()

strat_name = "1-Hour Weekly R3 Trigger -> 5-Min Weekly R2 + RSI>85 Short (TP VWAP | SL 3%)"

for json_file in ['data/strategies.json', 'data/backtest_strategies.json']:
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    updated = False
    for item in data:
        if item.get('name') == strat_name:
            item['code'] = strat_code
            updated = True
            break
            
    if updated:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        print(f"Successfully updated '{strat_name}' in {json_file}")
    else:
        print(f"Warning: '{strat_name}' not found in {json_file}")

import json

def inspect(title, path):
    print(f"\n=== {title} ===")
    with open(path, 'r', encoding='utf-8') as f:
        strats = json.load(f)
    for i, s in enumerate(strats):
        code = s.get('code', '')
        print(f"\n[{i}] {s.get('name')}")
        lines = code.splitlines()
        for idx, line in enumerate(lines):
            l = line.strip()
            if any(k in l for k in ['End of Data', 'Still Running', 'OPEN_TIMEOUT', 'open_timeout', "'is_open'", '"is_open"', 'close_trade(']):
                print(f"    L{idx+1}: {l}")

inspect('backtest_strategies.json', 'data/backtest_strategies.json')
inspect('strategies.json', 'data/strategies.json')

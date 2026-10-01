import json

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt = json.load(f)

print(f"Total backtest strategies: {len(bt)}")
for idx, s in enumerate(bt):
    code = s.get('code', '')
    has_sim = 'def simulate_trades' in code
    has_trades = '"trades"' in code or "'trades'" in code
    has_open = '"is_open"' in code or "'is_open'" in code
    has_still_running = 'Still Running' in code
    has_end_of_data = 'End of Data' in code
    has_timeout = 'OPEN_TIMEOUT' in code
    print(f"{idx+1}. {s['name']}")
    print(f"   simulate_trades: {has_sim} | trades: {has_trades} | is_open: {has_open} | Still Running: {has_still_running} | End of Data: {has_end_of_data} | OPEN_TIMEOUT: {has_timeout}")

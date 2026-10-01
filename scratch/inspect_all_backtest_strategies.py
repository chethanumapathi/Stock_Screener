import json

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    strats = json.load(f)

print(f"Total strategies in backtest_strategies.json: {len(strats)}")
for i, s in enumerate(strats):
    code = s.get('code', '')
    has_sim = 'def simulate_trades' in code
    has_trades = "'trades': trades" in code or '"trades": trades' in code
    has_open_str = "'is_open'" in code or '"is_open"' in code
    has_still_running = "Still Running" in code
    has_end_of_data = "End of Data" in code
    has_open_timeout = "OPEN_TIMEOUT" in code or "open_timeout" in code
    print(f"[{i}] {s.get('name')}")
    print(f"    sim: {has_sim}, trades: {has_trades}, is_open: {has_open_str}, Still Running: {has_still_running}, End of Data: {has_end_of_data}, timeout: {has_open_timeout}")

with open('data/strategies.json', 'r', encoding='utf-8') as f:
    s_strats = json.load(f)
print(f"\nTotal strategies in strategies.json: {len(s_strats)}")
for i, s in enumerate(s_strats):
    code = s.get('code', '')
    has_sim = 'def simulate_trades' in code
    has_trades = "'trades': trades" in code or '"trades": trades' in code
    has_still_running = "Still Running" in code
    has_end_of_data = "End of Data" in code
    has_open_timeout = "OPEN_TIMEOUT" in code or "open_timeout" in code
    print(f"[{i}] {s.get('name')}")
    print(f"    sim: {has_sim}, trades: {has_trades}, Still Running: {has_still_running}, End of Data: {has_end_of_data}, timeout: {has_open_timeout}")

import sys
import os
sys.path.insert(0, os.path.abspath('.'))
import json
from app import run_backtest_simulation

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    strats = json.load(f)

best_swing = None
for s in strats:
    if 'Best Swing' in s.get('name', ''):
        best_swing = s
        break

if best_swing:
    print("Testing strategy:", best_swing['name'])
    res = run_backtest_simulation(best_swing['code'], timeframe='1d', segment='all')
    trades = res.get('trades', [])
    print(f"Total trades returned by run_backtest_simulation: {len(trades)}")
    
    running = [t for t in trades if t.get('is_open') or t.get('exit_reason') == 'Still Running']
    print(f"Still running trades count: {len(running)}")
    for r in running:
        print(f"  Symbol: {r.get('symbol'):<12} Entry: {r.get('entry_date')} Exit: {r.get('exit_date')} Reason: {r.get('exit_reason'):<15} Dur: {r.get('duration'):<15} PnL%: {r.get('pnl_pct')}% MTM: INR {r.get('mtm_pnl')}")
    
    overall = res.get('overall_report', {})
    print("\nOverall Report:")
    print(f"  still_running_trades: {overall.get('still_running_trades')}")
    print(f"  still_running_mtm: INR {overall.get('still_running_mtm')}")
    print(f"  still_running_str: {overall.get('still_running_str')}")
    print(f"  no_of_trades (closed): {overall.get('no_of_trades')}")
    print(f"  overall_profit: INR {overall.get('overall_profit')}")

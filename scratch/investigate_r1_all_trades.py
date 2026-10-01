import os
import sys
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
import json
import glob
from app import run_backtest_simulation

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_data = json.load(f)

strat = next((s for s in bt_data if 'Best Swing Trade - Weekly Yearly-R1' in s.get('name', '')), None)

print(f"Running simulation on all parquet symbols for '{strat['name']}'...")
res = run_backtest_simulation(
    code_str=strat['code'],
    segment='all',
    timeframe='1d',
    capital_per_trade=100000.0,
    slippage_pct=0.1,
    min_market_cap_cr=0.0
)

trades = res.get('trades', [])
overall = res.get('overall_report', {})

print("\n--- OVERALL REPORT ---")
print("Total Trades:", overall.get('no_of_trades'))
print("Open Trades:", overall.get('open_trades'))
print("Still Running Trades:", overall.get('still_running_trades'))
print("Still Running MTM:", overall.get('still_running_mtm'))
print("Still Running Str:", repr(overall.get('still_running_str')))

running = [t for t in trades if t.get('is_open') is True or t.get('exit_reason') == 'Still Running']
closed = [t for t in trades if not (t.get('is_open') is True or t.get('exit_reason') == 'Still Running')]
print(f"\nTotal trades in result: {len(trades)}")
print(f"Running trades: {len(running)}")
print(f"Closed trades: {len(closed)}")

print("\nAll Running Trades:")
for t in running:
    print(f"  {t['symbol']:<12} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} | Reason: {t['exit_reason']} | ExitPrice: {t['exit_price']} | PnL: Rs {t['net_pnl']} ({t['pnl_pct']}%) | is_open: {t.get('is_open')}")

# Check closed trades with suspicious exit dates or reasons:
sus = [t for t in closed if 'end of data' in str(t.get('exit_reason')).lower() or 'timeout' in str(t.get('exit_reason')).lower() or 'running' in str(t.get('exit_reason')).lower() or str(t.get('exit_date')) == '-' or str(t.get('exit_date')).startswith('2026-09-28') or str(t.get('exit_date')).startswith('28-Sep-2026')]
print(f"\nSuspicious closed trades: {len(sus)}")
for t in sus:
    print(f"  SUS: {t['symbol']:<12} | Entry: {t['entry_date']} | Exit: {t['exit_date']} | Reason: {t['exit_reason']} | is_open: {t.get('is_open')}")

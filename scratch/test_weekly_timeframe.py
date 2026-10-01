import os
import sys
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
import json
import glob
from app import run_backtest_simulation

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_data = json.load(f)

strat = next((s for s in bt_data if 'Best Swing Trade' in s.get('name', '')), None)

parquet_files = sorted(glob.glob('data/adjusted_daily/*.parquet'))
symbols = [os.path.basename(p).replace('.parquet', '') for p in parquet_files[:200]]

print(f"Running simulation with timeframe='1w'...")
res = run_backtest_simulation(
    code_str=strat['code'],
    segment='watchlist',
    watchlist_symbols=symbols,
    timeframe='1w',
    capital_per_trade=100000.0,
    slippage_pct=0.1,
    min_market_cap_cr=0.0
)

overall = res.get('overall_report', {})
trades = res.get('trades', [])

print("Overall report:")
for k, v in overall.items():
    print(f"  {k}: {v}")

running = [t for t in trades if t.get('is_open') is True or t.get('exit_reason') == 'Still Running']
print(f"Total trades: {len(trades)}")
print(f"Running trades: {len(running)}")
for t in running:
    print(f"  {t['symbol']:<10} Entry: {t['entry_date']} | Exit: {t['exit_date']} | Reason: {t['exit_reason']} | is_open: {t.get('is_open')}")

# Also check trades with exit date near end of data:
ends = [t for t in trades if str(t.get('exit_date')) in ['2026-09-25', '2026-09-28', '25-Sep-2026', '28-Sep-2026']]
print(f"Trades with exit date near end of data: {len(ends)}")
for t in ends:
    print(f"  {t['symbol']:<10} Entry: {t['entry_date']} | Exit: {t['exit_date']} | Reason: {t['exit_reason']} | is_open: {t.get('is_open')}")

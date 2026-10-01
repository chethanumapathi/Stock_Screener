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
assert strat is not None, "Strategy not found!"

parquet_files = sorted(glob.glob('data/adjusted_daily/*.parquet'))
symbols = [os.path.basename(p).replace('.parquet', '') for p in parquet_files[:200]]

print(f"Running simulation on {len(symbols)} symbols with '{strat['name']}'...")
res = run_backtest_simulation(
    code_str=strat['code'],
    segment='watchlist',
    watchlist_symbols=symbols,
    timeframe='1d',
    capital_per_trade=100000.0,
    slippage_pct=0.1,
    min_market_cap_cr=0.0
)

trades = res.get('trades', [])
overall = res.get('overall_report', {})

print("\n--- OVERALL REPORT ---")
for k, v in overall.items():
    print(f"  {k}: {v}")

running = [t for t in trades if t.get('is_open') is True or t.get('exit_reason') == 'Still Running']
print(f"\nTotal trades: {len(trades)}")
print(f"Running trades: {len(running)}")
for t in running[:10]:
    print(f"  {t['symbol']:<10} Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} | Reason: {t['exit_reason']} | ExitPrice: {t['exit_price']} | PnL: Rs {t['net_pnl']} ({t['pnl_pct']}%) | is_open: {t.get('is_open')}")

# Also check trades that might have ended on the last date but were NOT classified as running:
last_date_trades = [t for t in trades if str(t.get('exit_date')) == '2026-09-28' or str(t.get('exit_date')) == '28-Sep-2026' or str(t.get('exit_date')).startswith('2026-09-25')]
print(f"\nTrades with exit date around 2026-09-28 that are NOT running: {len([t for t in last_date_trades if not t.get('is_open')])}")
for t in last_date_trades[:10]:
    print(f"  {t['symbol']:<10} Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} | Reason: {t['exit_reason']} | is_open: {t.get('is_open')}")

import os
import sys
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
import json
import glob
from app import run_backtest_simulation

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_data = json.load(f)

strat = next((s for s in bt_data if 'Daily Monthly-R3 Breakout above Yearly-R2' in s.get('name', '')), None)
assert strat is not None, "Strategy not found in backtest_strategies.json!"

parquet_files = sorted(glob.glob('data/adjusted_daily/*.parquet'))
symbols = [os.path.basename(p).replace('.parquet', '') for p in parquet_files[:500]]

print(f"Running simulation on {len(symbols)} symbols...")
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
print("Total Trades:", overall.get('no_of_trades'))
print("Win Trades:", overall.get('win_trades'))
print("Loss Trades:", overall.get('loss_trades'))
print("Still Running Trades:", overall.get('still_running_trades'))
print("Still Running MTM:", overall.get('still_running_mtm'))
print("Still Running String:", repr(overall.get('still_running_str')))
print("Avg Profit on Winning:", overall.get('avg_profit_win_trade'))

running_trades = [t for t in trades if t.get('is_open') is True or t.get('exit_reason') == 'Still Running']
closed_trades = [t for t in trades if not (t.get('is_open') is True or t.get('exit_reason') == 'Still Running')]

print(f"\nTotal Running Trades found: {len(running_trades)}")
print(f"Total Closed Trades found: {len(closed_trades)}")

if running_trades:
    print("\nSample Running Trades:")
    for t in running_trades[:5]:
        print(f"Symbol: {t['symbol']:<10} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit Date: {t['exit_date']} | Exit Reason: {t['exit_reason']} | Exit Price (CMP): {t['exit_price']} | MTM PnL: Rs {t['net_pnl']} ({t['pnl_pct']}%)")

print("\nVerification check:")
any_running_with_date = any(t['exit_date'] != '-' for t in running_trades)
print(f"Any running trade with non-dash exit date? {any_running_with_date}")
assert not any_running_with_date, "Error: running trades should have exit_date == '-'"

all_running_status_ok = all(t['exit_reason'] == 'Still Running' for t in running_trades)
print(f"All running trades have status 'Still Running'? {all_running_status_ok}")
assert all_running_status_ok, "Error: all running trades should have exit_reason == 'Still Running'"

print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

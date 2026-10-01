import os
import sys
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
import json
from app import run_backtest_simulation

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_data = json.load(f)

strat = next((s for s in bt_data if 'Best Swing Trade' in s.get('name', '')), None)

for seg in ['nifty50', 'fno', 'nifty500']:
    print(f"\n================ Segment: {seg} ================")
    res = run_backtest_simulation(
        code_str=strat['code'],
        segment=seg,
        timeframe='1w',
        capital_per_trade=100000.0,
        slippage_pct=0.1,
        min_market_cap_cr=0.0
    )
    overall = res.get('overall_report', {})
    trades = res.get('trades', [])
    running = [t for t in trades if t.get('is_open') is True or t.get('exit_reason') == 'Still Running']
    print(f"Total: {len(trades)} | Closed: {overall.get('no_of_trades')} | Running: {overall.get('still_running_trades')} | MTM: {overall.get('still_running_mtm')}")
    for t in running:
        print(f"  RUNNING: {t['symbol']} | Entry: {t['entry_date']} | Exit: {t['exit_date']} | Reason: {t['exit_reason']} | ExitPrice: {t['exit_price']} | MTM: {t['net_pnl']} | is_open: {t.get('is_open')}")
    # Also check trades with exit date near end of data:
    for t in trades:
        if str(t.get('exit_date')) in ['2026-09-25', '2026-09-28', '25-Sep-2026', '28-Sep-2026'] and not t.get('is_open'):
            print(f"  CLOSED END: {t['symbol']} | Entry: {t['entry_date']} | Exit: {t['exit_date']} | Reason: {t['exit_reason']}")

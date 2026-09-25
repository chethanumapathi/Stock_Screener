import sys, os
sys.path.insert(0, os.path.abspath('.'))

from app import run_backtest_simulation, get_available_parquet_symbols
with open('strategies/fifteen_min_weekly_r3_r2_rsi80.py', 'r', encoding='utf-8') as f:
    code_str = f.read()

symbols = ['ELECON'] + [s for s in get_available_parquet_symbols() if s != 'ELECON'][:100]

res = run_backtest_simulation(
    code_str=code_str,
    segment='watchlist',
    timeframe='5m',
    watchlist_symbols=symbols,
    start_date='2025-01-01',
    end_date='2026-05-15',
    capital_per_trade=100000.0,
    slippage_pct=0.5,
    include_brokerage=True,
    include_taxes=True,
    brokerage_per_order=20.0,
    min_market_cap_cr=0.0
)

trades = res.get('trades', [])
tp_trades = [t for t in trades if 'Target Profit' in t['exit_reason']]
pos_tp = [t for t in tp_trades if t['net_pnl'] > 0]
neg_tp = [t for t in tp_trades if t['net_pnl'] <= 0]

print(f"Total Trades: {len(trades)}")
print(f"Target Profit Trades: {len(tp_trades)} | Positive: {len(pos_tp)} | Negative: {len(neg_tp)}")

print("\nAll ELECON Trades:")
for t in trades:
    if t['symbol'] == 'ELECON':
        print(f"  {t['symbol']} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} @ {t['exit_price']} | Reason: {t['exit_reason']} | Net PnL: Rs {t['net_pnl']} ({t['pnl_pct']}%)")

if neg_tp:
    print("\nNegative TP Trades (if any):")
    for t in neg_tp:
        print(f"  {t['symbol']} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} @ {t['exit_price']} | Net PnL: Rs {t['net_pnl']}")
else:
    print("\nSUCCESS: 0 Negative Target Profit trades across the tested stocks!")

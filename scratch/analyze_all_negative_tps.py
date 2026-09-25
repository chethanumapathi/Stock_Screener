import os
import sys
sys.path.insert(0, os.path.abspath('.'))

from app import run_backtest_simulation, get_available_parquet_symbols

with open('strategies/fifteen_min_weekly_r3_r2_rsi80.py', 'r', encoding='utf-8') as f:
    code_str = f.read()

symbols = get_available_parquet_symbols()[:300]

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
print(f"Total Trades (300 stocks, 2025-2026): {len(trades)}")

neg_tp = []
pos_tp = []
for t in trades:
    if 'Target Profit' in t['exit_reason']:
        gross_pts = t['entry_price'] - t['exit_price']
        gross_pct = (gross_pts / t['entry_price']) * 100.0
        if t['net_pnl'] < 0:
            neg_tp.append((t, gross_pct))
        else:
            pos_tp.append((t, gross_pct))

print(f"Positive TP Trades: {len(pos_tp)}")
print(f"Negative TP Trades: {len(neg_tp)}")

print("\nSample Negative TP Trades:")
for t, g_pct in neg_tp[:10]:
    print(f"  {t['symbol']} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} @ {t['exit_price']} | Gross: {g_pct:.2f}% | Net PnL: Rs {t['net_pnl']} ({t['pnl_pct']}%)")

import os
import sys
sys.path.insert(0, os.path.abspath('.'))

import pandas as pd
from app import run_backtest_simulation

with open('strategies/fifteen_min_weekly_r3_r2_rsi80.py', 'r', encoding='utf-8') as f:
    code_str = f.read()

from app import get_available_parquet_symbols

all_syms = get_available_parquet_symbols()
# Include ELECON and other popular stocks
target_syms = ['ELECON'] + [s for s in all_syms if s != 'ELECON'][:150]

res = run_backtest_simulation(
    code_str=code_str,
    segment='watchlist',
    timeframe='5m',
    watchlist_symbols=target_syms,
    start_date='2026-05-01',
    end_date='2026-05-15',
    capital_per_trade=100000.0,
    slippage_pct=0.5,
    include_brokerage=True,
    include_taxes=True,
    brokerage_per_order=20.0,
    min_market_cap_cr=0.0
)

trades = res.get('trades', [])
print(f"Total FNO Trades: {len(trades)}")

neg_tp_trades = []
for t in trades:
    gross = (t['entry_price'] - t['exit_price']) / t['entry_price'] * 100.0 if t['type'] == 'Short' else (t['exit_price'] - t['entry_price']) / t['entry_price'] * 100.0
    if 'Target Profit' in t['exit_reason'] and t['net_pnl'] < 0:
        neg_tp_trades.append(t)
        print(f"Negative TP: {t['symbol']} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} @ {t['exit_price']} | Gross: {gross:.2f}% | Net PnL: Rs {t['net_pnl']} ({t['pnl_pct']}%) | Reason: {t['exit_reason']}")

print(f"\nTotal Negative TP Trades: {len(neg_tp_trades)} out of {len(trades)} trades")

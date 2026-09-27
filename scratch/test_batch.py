import sys
sys.path.append('.')
import os
import pandas as pd
from strategies.daily_monthly_r3_yearly_r2_breakout import backtest

stocks = ['ACE', 'AAATECH', '3PLAND', 'TATASTEEL', 'BEL', 'HAL', 'RELIANCE', 'INFY']
for s in stocks:
    p = f'data/adjusted_daily/{s}.parquet'
    if not os.path.exists(p):
        continue
    df = pd.read_parquet(p)
    res = backtest(df)
    trades = res['trades']
    print(f"{s:<10} | Total Trades: {len(trades)}")
    for t in trades:
        pnl = round((t['exit_price'] - t['entry_price']) / t['entry_price'] * 100, 2)
        print(f"   Entry: {t['entry_date']} @ {t['entry_price']:<8.2f} | Exit: {t['exit_date']} @ {t['exit_price']:<8.2f} ({pnl:>6.2f}%) | {t['exit_reason']}")

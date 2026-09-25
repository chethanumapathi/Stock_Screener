import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time as dtime

from strategies.five_min_daily_r3_rsi85_ema50_sl import (
    backtest,
    simulate_trades,
    compute_rsi,
    compute_ema,
    compute_daily_r3,
    compute_daily_260_ema,
    _prepare_5min_df
)
from app import validate_backtest_code

def test_validator():
    print("=== TEST 1: App.py Backtest Validator ===")
    with open('strategies/five_min_daily_r3_rsi85_ema50_sl.py', 'r', encoding='utf-8') as f:
        code = f.read()
    valid, err, func = validate_backtest_code(code)
    assert valid, f"Validation failed: {err}"
    print("PASS: validate_backtest_code passed successfully!\n")

def test_daily_260_ema_filter():
    print("=== TEST 2: Daily 260 EMA Filter Test (Allowed Below EMA, Blocked Above EMA) ===")
    
    # 10 days of data (750 bars)
    dates = []
    curr = pd.Timestamp('2024-01-01 09:15:00')
    while len(dates) < 750:
        if curr.weekday() < 5:
            day_start = curr.replace(hour=9, minute=15)
            for b in range(75):
                dates.append(day_start + timedelta(minutes=5 * b))
        curr += timedelta(days=1)
        
    df = pd.DataFrame(index=pd.DatetimeIndex(dates))
    df['open'] = 200.0
    df['high'] = 201.0
    df['low'] = 199.0
    df['close'] = 200.0
    df['volume'] = 50000.0

    # Days 0-3: close around 200.0 -> Daily 260 EMA is ~180-200.
    # Day 4 (bars 300 to 374): prior day drops to High=110, Low=90, Close=100 -> Daily Pivot = 100, Daily R3 = 130.0!
    df.iloc[300:375, df.columns.get_loc('high')] = 110.0
    df.iloc[300:375, df.columns.get_loc('low')] = 90.0
    df.iloc[300:375, df.columns.get_loc('close')] = 100.0

    # Day 5 (bars 375-450):
    for b in range(375, 380):
        df.iloc[b, df.columns.get_loc('open')] = 100.0 + (b - 375) * 5
        df.iloc[b, df.columns.get_loc('close')] = 105.0 + (b - 375) * 5
        df.iloc[b, df.columns.get_loc('high')] = 106.0 + (b - 375) * 5
        df.iloc[b, df.columns.get_loc('low')] = 99.0 + (b - 75) * 5

    # Bar 380: Trigger candle
    # Close = 133.0 (> Daily R3 130.0, RSI > 85, and Close = 133.0 < Daily 260 EMA ~180.0)
    df.iloc[380, df.columns.get_loc('open')] = 128.0
    df.iloc[380, df.columns.get_loc('close')] = 133.0
    df.iloc[380, df.columns.get_loc('high')] = 135.0
    df.iloc[380, df.columns.get_loc('low')] = 127.0

    # Bar 381: Price drops to 50 EMA (~107) -> Hits Target Profit!
    df.iloc[381, df.columns.get_loc('open')] = 130.0
    df.iloc[381, df.columns.get_loc('high')] = 130.0
    df.iloc[381, df.columns.get_loc('low')] = 95.0
    df.iloc[381, df.columns.get_loc('close')] = 100.0

    # Case A: When Close (133) < Daily 260 EMA (180), trade is ALLOWED!
    res_allowed = backtest(df.copy())
    trades_allowed = res_allowed['trades']
    assert len(trades_allowed) == 1, f"Expected 1 trade when Close < 260 EMA, got {len(trades_allowed)}"
    t = trades_allowed[0]
    assert t['entry_price'] == 133.0
    assert "Target Profit" in t['exit_reason']
    print(f"PASS Case A: Trade executed when Close < Daily 260 EMA! Exit: {t['exit_reason']}")

    # Case B: When all prior days were at 100.0 so Daily 260 EMA is ~100.0.
    # Close (133.0) is ABOVE Daily 260 EMA (~100.0) -> Trade must be BLOCKED!
    df_blocked = df.copy()
    df_blocked.iloc[0:375, df_blocked.columns.get_loc('close')] = 100.0
    df_blocked.iloc[0:375, df_blocked.columns.get_loc('high')] = 110.0
    df_blocked.iloc[0:375, df_blocked.columns.get_loc('low')] = 90.0

    res_blocked = backtest(df_blocked)
    trades_blocked = res_blocked['trades']
    assert len(trades_blocked) == 0, f"Expected 0 trades when Close > 260 EMA (blocked), got {len(trades_blocked)}"
    print("PASS Case B: Trade successfully blocked when Close > Daily 260 EMA!\n")

if __name__ == '__main__':
    test_validator()
    test_daily_260_ema_filter()
    print("ALL TESTS INCLUDING 260 EMA FILTER PASSED PERFECTLY!")

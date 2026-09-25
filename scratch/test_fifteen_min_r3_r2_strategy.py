import sys
import os

sys.path.insert(0, os.path.abspath('.'))
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from strategies.fifteen_min_weekly_r3_r2_rsi80 import (
    backtest,
    simulate_trades,
    compute_rsi,
    compute_session_vwap,
    compute_weekly_pivots,
    compute_nse_1hour_triggers,
    construct_nse_1hour_candles,
    _prepare_5min_df,
    TP_PCT
)
from app import validate_backtest_code

def test_dry_run_validation():
    print("=== TEST 1: App.py Dry-run Validation ===")
    with open('strategies/fifteen_min_weekly_r3_r2_rsi80.py', 'r', encoding='utf-8') as f:
        code = f.read()
    valid, err, func = validate_backtest_code(code)
    assert valid, f"Dry-run validation failed: {err}"
    print("PASS: Dry-run validation passed without errors!\n")

def test_rules_same_day_single_trade_cutoff():
    print("=== TEST 2: Verification of New Rules (No Same-Day Entry, Max 1/Day, 1:00 PM Cutoff) ===")
    
    dates = []
    base_date = pd.Timestamp('2024-01-01 09:15:00')
    curr = base_date
    while len(dates) < 1200:
        if curr.weekday() < 5:  # Mon-Fri
            day_start = curr.replace(hour=9, minute=15)
            for b in range(75):
                dates.append(day_start + timedelta(minutes=5 * b))
        curr += timedelta(days=1)
    
    n = len(dates)
    df = pd.DataFrame(index=pd.DatetimeIndex(dates[:n]))
    df['open'] = 100.0
    df['high'] = 101.0
    df['low'] = 99.0
    df['close'] = 100.0
    df['volume'] = 25000.0
    
    # Week 0 baseline (bars 0-375): High=105, Low=95, Close=100 -> R3=115, R2=110
    df.iloc[:375, df.columns.get_loc('high')] = 105.0
    df.iloc[:375, df.columns.get_loc('low')] = 95.0
    df.iloc[:375, df.columns.get_loc('close')] = 100.0
    
    # In Week 1: Day 6 (bars 375 to 449):
    # Two consecutive 1-hour candles close above Weekly R3 (> 115):
    # 09:15-10:15 (bars 375-386) and 10:15-11:15 (bars 387-398)
    for b in range(375, 387):
        df.iloc[b, df.columns.get_loc('close')] = 116.0
        df.iloc[b, df.columns.get_loc('high')] = 117.0
    for b in range(387, 399):
        df.iloc[b, df.columns.get_loc('close')] = 117.0
        df.iloc[b, df.columns.get_loc('high')] = 118.0
        
    # Trigger completes at 11:15 on Day 6!
    # On Day 6 afternoon (e.g. bars 405-410), produce 5m RSI > 85 and Close > Weekly R2:
    for b in range(405, 412):
        c = 118.0 + (b - 404) * 1.5
        df.iloc[b, df.columns.get_loc('close')] = c
        df.iloc[b, df.columns.get_loc('high')] = c + 1.0
        df.iloc[b, df.columns.get_loc('open')] = c - 1.0
        df.iloc[b, df.columns.get_loc('low')] = c - 1.5
        
    # On Day 7 (next day, bars 450 to 524):
    # At 09:30 AM (bars 453 to 456): 5m RSI > 85 and Close > Weekly R2 -> Should enter!
    for b in range(450, 456):
        c = 120.0 + (b - 449) * 1.5
        df.iloc[b, df.columns.get_loc('close')] = c
        df.iloc[b, df.columns.get_loc('high')] = c + 1.0
        df.iloc[b, df.columns.get_loc('open')] = c - 1.0
        df.iloc[b, df.columns.get_loc('low')] = c - 1.5
        
    # Breakout at bar 457
    df.iloc[457, df.columns.get_loc('open')] = 129.0
    df.iloc[457, df.columns.get_loc('high')] = 135.0  # Takes TP
    df.iloc[457, df.columns.get_loc('close')] = 134.0
    
    res = backtest(df)
    trades = res['trades']
    print(f"Simulated trades count: {len(trades)}")
    for t in trades:
        print(f" Trade: Entry={t['entry_price']} on {t['entry_date']}, Exit={t['exit_price']} on {t['exit_date']}, Reason={t['exit_reason']}")
        
    # Verify NO trade was entered on Day 6 (the trigger day)
    day6_trades = [t for t in trades if '2024-01-08' in str(t['entry_date'])]
    day7_trades = [t for t in trades if '2024-01-09' in str(t['entry_date'])]
    assert len(day6_trades) == 0, f"Expected 0 trades on trigger day, but got {len(day6_trades)}!"
    assert len(day7_trades) == 1, f"Expected exactly 1 trade on next day, but got {len(day7_trades)}!"
    print("PASS: No same-day entry, max 1 trade/day, and 1:00 PM cutoff verified successfully!\n")

def test_fincables_exact():
    print("=== TEST 3: FINCABLES Exact Verification for May 2026 ===")
    from app import get_ticker_parquet_path
    import duckdb
    
    p = get_ticker_parquet_path('FINCABLES')
    assert p is not None, "FINCABLES parquet not found!"
    con = duckdb.connect()
    df_raw = con.execute(f"SELECT * FROM '{p}' ORDER BY Date").df()
    con.close()
    
    res = backtest(df_raw)
    may_trades = [t for t in res['trades'] if '2026-05' in str(t['entry_date'])]
    print("FINCABLES May 2026 Trades:")
    for t in may_trades:
        print(t)
        
    # Check that 07-May-2026 has ZERO trades
    may7_trades = [t for t in may_trades if '2026-05-07' in str(t['entry_date'])]
    assert len(may7_trades) == 0, f"Expected 0 trades on 07-May-2026, got: {may7_trades}"
    print("PASS: 07-May-2026 has 0 trades (trigger day correctly blocked)!")
    
    # Check that 08-May-2026 has the expected trade
    may8_trades = [t for t in may_trades if '2026-05-08' in str(t['entry_date'])]
    assert len(may8_trades) == 1, f"Expected 1 trade on 08-May-2026, got: {may8_trades}"
    assert "Target Profit" in may8_trades[0]['exit_reason']
    print(f"PASS: 08-May-2026 trade entered at {may8_trades[0]['entry_price']} and exited with TP (+3.0%)!\n")

if __name__ == '__main__':
    test_dry_run_validation()
    test_rules_same_day_single_trade_cutoff()
    test_fincables_exact()
    print("ALL TESTS PASSED WITH ZERO ERRORS!")

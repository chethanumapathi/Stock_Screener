import sys
import os

sys.path.insert(0, os.path.abspath('.'))
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time as dtime

from strategies.fifteen_min_weekly_r3_r2_rsi80 import (
    backtest,
    simulate_trades,
    compute_rsi,
    compute_session_vwap,
    compute_weekly_pivots,
    _prepare_5min_df
)
from app import validate_backtest_code, compute_backtest_analytics

def test_dry_run_validation():
    print("=== TEST 1: App.py Dry-run Validation ===")
    with open('strategies/fifteen_min_weekly_r3_r2_rsi80.py', 'r', encoding='utf-8') as f:
        code = f.read()
    valid, err, func = validate_backtest_code(code)
    assert valid, f"Dry-run validation failed: {err}"
    print("PASS: Dry-run validation passed without errors!\n")

def test_synthetic_short_scenarios():
    print("=== TEST 2: Synthetic Short Scenarios (TP VWAP, SL 3%, PnL Direction) ===")
    
    # Generate 15 days of 5-minute bars (75 bars per day = 1125 bars)
    dates = []
    base_date = pd.Timestamp('2024-01-01 09:15:00')
    curr = base_date
    while len(dates) < 750:
        if curr.weekday() < 5:
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
    df['volume'] = 50000.0
    
    # Week 0 baseline (first 5 days = 375 bars)
    # High = 105, Low = 95, Close = 100 -> Weekly Pivot = 100, R2 = 110.0, R3 = 105 + 2*(100-95) = 115.0
    df.iloc[:375, df.columns.get_loc('high')] = 105.0
    df.iloc[:375, df.columns.get_loc('low')] = 95.0
    df.iloc[:375, df.columns.get_loc('close')] = 100.0
    
    # Week 1: Day 5 (Monday, bars 375-450)
    # Produce two consecutive 1-hour candles closing above Weekly R3 (115.0):
    # Slot 0 (09:15-10:15 = bars 375 to 386): Close = 118.0 > 115.0
    for b in range(375, 387):
        df.iloc[b, df.columns.get_loc('close')] = 118.0
        df.iloc[b, df.columns.get_loc('high')] = 119.0
        df.iloc[b, df.columns.get_loc('open')] = 117.0
        df.iloc[b, df.columns.get_loc('low')] = 116.0
    # Slot 1 (10:15-11:15 = bars 387 to 399): Close = 120.0 > 115.0
    for b in range(387, 399):
        df.iloc[b, df.columns.get_loc('close')] = 120.0
        df.iloc[b, df.columns.get_loc('high')] = 121.0
        df.iloc[b, df.columns.get_loc('open')] = 119.0
        df.iloc[b, df.columns.get_loc('low')] = 118.0
        
    # Trigger completes on Day 5 at 11:15!
    # Because of DISALLOW_SAME_DAY_ENTRY, Day 5 cannot have entries.
    
    # Day 6 (Tuesday, bars 450 to 525):
    # Warm up 5m RSI: bars 450 to 455 (keep close < Weekly R2 110.0)
    for b in range(450, 456):
        c = 100.0 + (b - 450) * 1.5
        df.iloc[b, df.columns.get_loc('open')] = c - 0.5
        df.iloc[b, df.columns.get_loc('close')] = c
        df.iloc[b, df.columns.get_loc('high')] = c + 0.5
        df.iloc[b, df.columns.get_loc('low')] = c - 0.5
        
    # Bar 456 (09:45): 5m Close = 122.0 > Weekly R2 (110.0), RSI > 85.0 -> Qualifying 5m Candle!
    # Marks High = 123.0
    df.iloc[456, df.columns.get_loc('open')] = 120.0
    df.iloc[456, df.columns.get_loc('close')] = 122.0
    df.iloc[456, df.columns.get_loc('high')] = 123.0
    df.iloc[456, df.columns.get_loc('low')] = 119.0
    
    # Bar 457 (09:50): Subsequent candle trades up to High = 123.5 >= 123.0 -> Enters SHORT at 123.0!
    # Session VWAP is around 115.0
    df.iloc[457, df.columns.get_loc('open')] = 122.0
    df.iloc[457, df.columns.get_loc('high')] = 123.5
    df.iloc[457, df.columns.get_loc('low')] = 121.0
    df.iloc[457, df.columns.get_loc('close')] = 121.5
    
    # Bar 458 (09:55): Price dumps down to Low = 114.0 <= VWAP (~115.0)!
    # Reaches Target Profit at VWAP!
    df.iloc[458, df.columns.get_loc('open')] = 121.0
    df.iloc[458, df.columns.get_loc('high')] = 121.2
    df.iloc[458, df.columns.get_loc('low')] = 114.0
    df.iloc[458, df.columns.get_loc('close')] = 114.5
    
    res = backtest(df)
    trades = res['trades']
    print(f"Simulated short trades count: {len(trades)}")
    assert len(trades) >= 1, "Expected at least 1 short trade!"
    t = trades[0]
    print(f"Short Trade: Entry={t['entry_price']} on {t['entry_date']}, Exit={t['exit_price']} on {t['exit_date']}, Reason={t['exit_reason']}")
    assert "VWAP" in t['exit_reason'], f"Expected VWAP TP exit, got: {t['exit_reason']}"
    assert t['exit_price'] < t['entry_price'], "Expected profitable short trade where exit < entry"
    assert t['entry_price'] == 123.0, f"Expected entry at qualifying high 123.0, got {t['entry_price']}"
    
    # Analytics check
    t_copy = dict(t)
    t_copy['qty'] = 100
    analytics = compute_backtest_analytics([t_copy])
    adj_trade = analytics['trades'][0]
    print(f"Analytics Output: Net PnL = {adj_trade['net_pnl']}, PnL % = {adj_trade['pnl_pct']}%")
    assert adj_trade['net_pnl'] > 0, f"Short trade should produce positive PnL when price drops, got: {adj_trade['net_pnl']}"
    print("PASS: Short trade TP at VWAP and PnL calculation verified successfully!\n")

def test_short_stop_loss():
    print("=== TEST 3: Short Stop Loss (+3.0% Hit) ===")
    dates = []
    base_date = pd.Timestamp('2024-01-01 09:15:00')
    curr = base_date
    while len(dates) < 750:
        if curr.weekday() < 5:
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
    df['volume'] = 50000.0
    
    # Week 0 baseline -> Weekly R2 = 110.0, Weekly R3 = 115.0
    df.iloc[:375, df.columns.get_loc('high')] = 105.0
    df.iloc[:375, df.columns.get_loc('low')] = 95.0
    df.iloc[:375, df.columns.get_loc('close')] = 100.0
    
    # Week 1: 1-hour triggers on Day 5
    for b in range(375, 387):
        df.iloc[b, df.columns.get_loc('close')] = 118.0
        df.iloc[b, df.columns.get_loc('high')] = 119.0
        df.iloc[b, df.columns.get_loc('low')] = 116.0
    for b in range(387, 399):
        df.iloc[b, df.columns.get_loc('close')] = 120.0
        df.iloc[b, df.columns.get_loc('high')] = 121.0
        df.iloc[b, df.columns.get_loc('low')] = 118.0
        
    # Day 6: Warmup (keep close < Weekly R2 110.0)
    for b in range(450, 456):
        c = 100.0 + (b - 450) * 1.5
        df.iloc[b, df.columns.get_loc('open')] = c - 0.5
        df.iloc[b, df.columns.get_loc('close')] = c
        df.iloc[b, df.columns.get_loc('high')] = c + 0.5
        df.iloc[b, df.columns.get_loc('low')] = c - 0.5
        
    # Bar 456: Qualifying 5m Candle (High = 123.0)
    df.iloc[456, df.columns.get_loc('open')] = 120.0
    df.iloc[456, df.columns.get_loc('close')] = 122.0
    df.iloc[456, df.columns.get_loc('high')] = 123.0
    df.iloc[456, df.columns.get_loc('low')] = 119.0
    
    # Bar 457: Enters SHORT at 123.0! Stop Loss = 123.0 * 1.03 = 126.69 (+3.0%).
    df.iloc[457, df.columns.get_loc('open')] = 122.0
    df.iloc[457, df.columns.get_loc('high')] = 123.5
    df.iloc[457, df.columns.get_loc('low')] = 121.0
    df.iloc[457, df.columns.get_loc('close')] = 122.5
    
    # Bar 458: Price surges above Stop Loss (High = 127.5 >= 126.69)!
    # Keep low above VWAP so it does not trigger TP
    df.iloc[458, df.columns.get_loc('open')] = 123.0
    df.iloc[458, df.columns.get_loc('high')] = 127.5
    df.iloc[458, df.columns.get_loc('low')] = 122.5
    df.iloc[458, df.columns.get_loc('close')] = 127.0
    
    res = backtest(df)
    trades = res['trades']
    assert len(trades) >= 1, "Expected trade"
    sl_trade = trades[0]
    print(f"SL Trade: Entry={sl_trade['entry_price']}, Exit={sl_trade['exit_price']}, Reason={sl_trade['exit_reason']}")
    assert "Stop Loss" in sl_trade['exit_reason']
    assert sl_trade['exit_price'] > sl_trade['entry_price'], "Exit price should be higher on stopped out short"
    assert sl_trade['exit_price'] == 126.69, f"Expected SL at 126.69, got {sl_trade['exit_price']}"
    print("PASS: Short Stop Loss (+3.0%) executed cleanly!\n")

def test_real_parquet_execution():
    print("=== TEST 4: Real Parquet Data Execution (FINCABLES & other symbols) ===")
    from app import get_ticker_parquet_path
    import duckdb
    
    for sym in ['FINCABLES', '20MICRONS', 'RELIANCE']:
        p = get_ticker_parquet_path(sym)
        if not os.path.exists(p):
            print(f"Skipping {sym} (not downloaded)")
            continue
        con = duckdb.connect()
        df_raw = con.execute(f"SELECT * FROM '{p}' LIMIT 50000").df()
        con.close()
        
        date_col = next((c for c in df_raw.columns if c.lower() == 'date'), None)
        if date_col:
            df_raw = df_raw.sort_values(date_col).reset_index(drop=True)
        res = backtest(df_raw)
        trades = res.get('trades', [])
        signals = res.get('signal', pd.Series()).sum()
        print(f"Symbol {sym}: {len(df_raw)} 1-min bars -> {len(res['df'])} 5-min bars | Signals: {signals} | Short Trades: {len(trades)}")
        if len(trades) > 0:
            for t in trades[:3]:
                print(f"   -> Trade: {t['entry_date']} @ {t['entry_price']} -> {t['exit_date']} @ {t['exit_price']} | {t['exit_reason']}")
    
    print("\nPASS: Real parquet data tested cleanly without errors!")

if __name__ == '__main__':
    test_dry_run_validation()
    test_synthetic_short_scenarios()
    test_short_stop_loss()
    test_real_parquet_execution()
    print("ALL SHORT STRATEGY 3 TESTS PASSED PERFECTLY!")

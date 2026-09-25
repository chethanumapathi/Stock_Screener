import sys
import os

sys.path.insert(0, os.path.abspath('.'))
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from strategies.intraday_rsi_volume_vwap_r2 import (
    backtest,
    simulate_trades,
    compute_rsi,
    compute_session_vwap,
    compute_daily_pivot_r2,
    _prepare_15min_df
)
from app import validate_backtest_code, compute_backtest_analytics

def test_dry_run_validation():
    print("=== TEST 1: App.py Dry-run Validation ===")
    with open('strategies/intraday_rsi_volume_vwap_r2.py', 'r', encoding='utf-8') as f:
        code = f.read()
    valid, err, func = validate_backtest_code(code)
    assert valid, f"Dry-run validation failed: {err}"
    print("PASS: Dry-run validation passed without errors!\n")

def test_synthetic_short_scenarios():
    print("=== TEST 2: Synthetic Short Scenarios (TP VWAP, SL 2%, PnL Direction) ===")
    
    # Generate 5 days of 15-minute bars (25 bars per day = 125 bars)
    dates = []
    base_date = pd.Timestamp('2024-01-01 09:15:00')
    curr = base_date
    while len(dates) < 125:
        if curr.weekday() < 5:
            day_start = curr.replace(hour=9, minute=15)
            for b in range(25):
                dates.append(day_start + timedelta(minutes=15 * b))
        curr += timedelta(days=1)
        
    n = len(dates)
    df = pd.DataFrame(index=pd.DatetimeIndex(dates[:n]))
    df['open'] = 100.0
    df['high'] = 101.0
    df['low'] = 99.0
    df['close'] = 100.0
    df['volume'] = 50000.0
    
    # Day 0 baseline (bars 0-25): High=105, Low=95, Close=100 -> Daily R2 = 100 + (105-95) = 110.0
    df.iloc[:25, df.columns.get_loc('high')] = 105.0
    df.iloc[:25, df.columns.get_loc('low')] = 95.0
    df.iloc[:25, df.columns.get_loc('close')] = 100.0
    df.iloc[:25, df.columns.get_loc('volume')] = 50000.0
    
    # Day 1: bars 25 to 50. Daily R2 is 110.0.
    # Warm up RSI: bars 25 to 30 rising with volume < 200,000
    for b in range(25, 31):
        c = 110.0 + (b - 24) * 2.0
        df.iloc[b, df.columns.get_loc('close')] = c
        df.iloc[b, df.columns.get_loc('high')] = c + 1.0
        df.iloc[b, df.columns.get_loc('open')] = c - 1.0
        df.iloc[b, df.columns.get_loc('low')] = c - 1.0
        df.iloc[b, df.columns.get_loc('volume')] = 150000.0  # Below 200k floor!
        
    # Candle 1 (bar 31): Close = 124.0 > 110, RSI > 80, Vol = 250,000 >= 200k
    df.iloc[31, df.columns.get_loc('open')] = 122.0
    df.iloc[31, df.columns.get_loc('close')] = 124.0
    df.iloc[31, df.columns.get_loc('high')] = 125.0
    df.iloc[31, df.columns.get_loc('low')] = 121.5
    df.iloc[31, df.columns.get_loc('volume')] = 300000.0
    
    # Candle 2 (bar 32): Close = 128.0 > 110, RSI > 85, Vol = 500,000 (highest in 2 months!)
    df.iloc[32, df.columns.get_loc('open')] = 124.0
    df.iloc[32, df.columns.get_loc('close')] = 128.0
    df.iloc[32, df.columns.get_loc('high')] = 129.0
    df.iloc[32, df.columns.get_loc('low')] = 123.5
    df.iloc[32, df.columns.get_loc('volume')] = 500000.0
    
    # Signal fires at bar 32! Enters SHORT at Close = 128.0.
    # Target is Session VWAP. VWAP on Day 1 is around 118.0.
    # Bar 33: Dumps down to 115.0! Low breaks below Session VWAP -> Exits with TP (VWAP Reached)!
    df.iloc[33, df.columns.get_loc('open')] = 127.0
    df.iloc[33, df.columns.get_loc('high')] = 127.5
    df.iloc[33, df.columns.get_loc('low')] = 115.0
    df.iloc[33, df.columns.get_loc('close')] = 117.0
    df.iloc[33, df.columns.get_loc('volume')] = 200000.0
    
    res = backtest(df)
    trades = res['trades']
    print(f"Simulated short trades count: {len(trades)}")
    assert len(trades) >= 1, "Expected at least 1 short trade!"
    t = trades[0]
    print(f"Short Trade: Entry={t['entry_price']} on {t['entry_date']}, Exit={t['exit_price']} on {t['exit_date']}, Reason={t['exit_reason']}")
    assert "VWAP" in t['exit_reason'], f"Expected VWAP TP exit, got: {t['exit_reason']}"
    assert t['exit_price'] < t['entry_price'], "Expected profitable short trade where exit < entry"
    
    # Test institutional analytics calculation in app.py for this short trade
    t_copy = dict(t)
    t_copy['qty'] = 100
    analytics = compute_backtest_analytics([t_copy])
    adj_trade = analytics['trades'][0]
    print(f"Analytics Output: Net PnL = {adj_trade['net_pnl']}, PnL % = {adj_trade['pnl_pct']}%")
    assert adj_trade['net_pnl'] > 0, f"Short trade should produce positive PnL when price drops, got: {adj_trade['net_pnl']}"
    assert adj_trade['pnl_pct'] > 0, f"Short trade should produce positive PnL %, got: {adj_trade['pnl_pct']}"
    print("PASS: Short trade TP at VWAP and PnL calculation verified successfully!\n")

def test_short_stop_loss():
    print("=== TEST 3: Short Stop Loss (+2.0% Hit) ===")
    dates = []
    base_date = pd.Timestamp('2024-01-01 09:15:00')
    curr = base_date
    while len(dates) < 125:
        if curr.weekday() < 5:
            day_start = curr.replace(hour=9, minute=15)
            for b in range(25):
                dates.append(day_start + timedelta(minutes=15 * b))
        curr += timedelta(days=1)
        
    n = len(dates)
    df = pd.DataFrame(index=pd.DatetimeIndex(dates[:n]))
    df['open'] = 100.0
    df['high'] = 101.0
    df['low'] = 99.0
    df['close'] = 100.0
    df['volume'] = 50000.0
    
    # Day 0 baseline -> Daily R2 = 110.0
    df.iloc[:25, df.columns.get_loc('high')] = 105.0
    df.iloc[:25, df.columns.get_loc('low')] = 95.0
    df.iloc[:25, df.columns.get_loc('close')] = 100.0
    
    # Day 1: Warmup
    for b in range(25, 31):
        c = 110.0 + (b - 24) * 2.0
        df.iloc[b, df.columns.get_loc('close')] = c
        df.iloc[b, df.columns.get_loc('high')] = c + 1.0
        df.iloc[b, df.columns.get_loc('low')] = c - 1.0
        df.iloc[b, df.columns.get_loc('volume')] = 150000.0
        
    # Candle 1 (bar 31)
    df.iloc[31, df.columns.get_loc('open')] = 122.0
    df.iloc[31, df.columns.get_loc('close')] = 124.0
    df.iloc[31, df.columns.get_loc('high')] = 125.0
    df.iloc[31, df.columns.get_loc('low')] = 121.5
    df.iloc[31, df.columns.get_loc('volume')] = 300000.0
    
    # Candle 2 (bar 32): Entry SHORT at Close = 128.0
    df.iloc[32, df.columns.get_loc('open')] = 124.0
    df.iloc[32, df.columns.get_loc('close')] = 128.0
    df.iloc[32, df.columns.get_loc('high')] = 129.0
    df.iloc[32, df.columns.get_loc('low')] = 127.0
    df.iloc[32, df.columns.get_loc('volume')] = 500000.0
    
    # Short Entry at 128.0. Stop Loss is 128.0 * 1.02 = 130.56 (+2.0%).
    # Bar 33: Rallies above SL (High = 131.0)!
    df.iloc[33, df.columns.get_loc('open')] = 128.5
    df.iloc[33, df.columns.get_loc('high')] = 131.0
    df.iloc[33, df.columns.get_loc('low')] = 128.0
    df.iloc[33, df.columns.get_loc('close')] = 130.0
    
    res = backtest(df)
    trades = res['trades']
    assert len(trades) >= 1, "Expected trade"
    sl_trade = trades[0]
    print(f"SL Trade: Entry={sl_trade['entry_price']}, Exit={sl_trade['exit_price']}, Reason={sl_trade['exit_reason']}")
    assert "Stop Loss" in sl_trade['exit_reason']
    assert sl_trade['exit_price'] > sl_trade['entry_price'], "Exit price should be higher on stopped out short"
    print("PASS: Short Stop Loss (+2.0%) executed cleanly!\n")

def test_real_parquet_execution():
    print("=== TEST 4: Real Parquet Data Execution ===")
    from app import get_available_parquet_symbols, get_ticker_parquet_path
    import duckdb
    
    symbols = get_available_parquet_symbols()
    print(f"Found {len(symbols)} parquet symbols.")
    
    for sym in symbols[:3]:
        p = get_ticker_parquet_path(sym)
        con = duckdb.connect()
        df_raw = con.execute(f"SELECT * FROM '{p}' LIMIT 50000").df()
        con.close()
        
        date_col = next((c for c in df_raw.columns if c.lower() == 'date'), None)
        if date_col:
            df_raw = df_raw.sort_values(date_col).reset_index(drop=True)
        res = backtest(df_raw)
        trades = res.get('trades', [])
        signals = res.get('signal', pd.Series()).sum()
        print(f"Symbol {sym}: {len(df_raw)} 1-min bars -> {len(res['df'])} 15-min bars | Signals: {signals} | Short Trades: {len(trades)}")
    
    print("\nPASS: Real parquet data tested cleanly without errors!")

if __name__ == '__main__':
    test_dry_run_validation()
    test_synthetic_short_scenarios()
    test_short_stop_loss()
    test_real_parquet_execution()
    print("ALL SHORT STRATEGY 1 TESTS PASSED PERFECTLY!")

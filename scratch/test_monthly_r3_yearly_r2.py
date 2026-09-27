import os
import glob
import pandas as pd
import numpy as np

def compute_pivots(df: pd.DataFrame):
    """
    Computes Classical Monthly R3 and Yearly R2 strictly from PRIOR completed periods.
    """
    if 'date' in df.columns:
        df['datetime'] = pd.to_datetime(df['date'])
    elif isinstance(df.index, pd.DatetimeIndex):
        df['datetime'] = df.index
    else:
        df['datetime'] = pd.to_datetime(df.index)

    df = df.sort_values('datetime').copy()
    
    # Yearly Period
    year_period = df['datetime'].dt.to_period('Y')
    yearly_ohlc = df.groupby(year_period).agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    )
    yearly_pp = (yearly_ohlc['high'] + yearly_ohlc['low'] + yearly_ohlc['close']) / 3.0
    yearly_r2 = yearly_pp + (yearly_ohlc['high'] - yearly_ohlc['low'])
    
    # Lag by 1 year for current year rows
    yearly_r2_shifted = yearly_r2.shift(1)
    df['Yearly_R2'] = year_period.map(yearly_r2_shifted).to_numpy(dtype=float)

    # Monthly Period
    month_period = df['datetime'].dt.to_period('M')
    monthly_ohlc = df.groupby(month_period).agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    )
    monthly_pp = (monthly_ohlc['high'] + monthly_ohlc['low'] + monthly_ohlc['close']) / 3.0
    monthly_r3 = monthly_ohlc['high'] + 2.0 * (monthly_pp - monthly_ohlc['low'])

    # Lag by 1 month for current month rows
    monthly_r3_shifted = monthly_r3.shift(1)
    df['Monthly_R3'] = month_period.map(monthly_r3_shifted).to_numpy(dtype=float)

    return df

# Test on 5 stocks
parquet_files = glob.glob('data/adjusted_daily/*.parquet')[:30]
print(f"Testing on {len(parquet_files)} stocks...")

total_trades = 0
for p in parquet_files:
    sym = os.path.basename(p).replace('.parquet', '')
    df = pd.read_parquet(p)
    if len(df) < 250:
        continue
    df = compute_pivots(df)
    
    close = df['close'].to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)
    dates = df['datetime'].dt.strftime('%Y-%m-%d').to_numpy()
    mr3 = df['Monthly_R3'].to_numpy(dtype=float)
    yr2 = df['Yearly_R2'].to_numpy(dtype=float)
    
    n = len(df)
    state = "IDLE" # IDLE, AWAITING_BREAKOUT, IN_TRADE
    qualifying_high = None
    trade_entry_idx = None
    entry_price = None
    tp_price = None
    
    trades = []
    
    for i in range(1, n):
        if np.isnan(mr3[i]) or np.isnan(yr2[i]):
            continue
            
        if state == "IDLE":
            # Qualification: Fresh close above Monthly R3 & Above Yearly R2
            fresh_mr3 = (close[i] > mr3[i]) and (np.isnan(mr3[i-1]) or close[i-1] <= mr3[i-1])
            above_yr2 = close[i] > yr2[i]
            
            if fresh_mr3 and above_yr2:
                qualifying_high = high[i]
                state = "AWAITING_BREAKOUT"
                continue
                
        elif state == "AWAITING_BREAKOUT":
            # Buy-stop when next candle breaks qualifying high
            if high[i] > qualifying_high:
                entry_price = max(open_[i], qualifying_high)
                tp_price = entry_price * 1.40
                trade_entry_idx = i
                state = "IN_TRADE"
                
                # Check intrabar TP on entry day
                if high[i] >= tp_price:
                    exit_price = max(open_[i], tp_price)
                    trades.append({
                        'sym': sym,
                        'entry_date': dates[i],
                        'entry_price': entry_price,
                        'exit_date': dates[i],
                        'exit_price': exit_price,
                        'reason': 'TP 40% (Same Bar)',
                        'pnl_pct': round((exit_price - entry_price)/entry_price * 100, 2)
                    })
                    state = "IDLE"
                    continue
                # Check SL on entry day
                elif close[i] < yr2[i]:
                    trades.append({
                        'sym': sym,
                        'entry_date': dates[i],
                        'entry_price': entry_price,
                        'exit_date': dates[i],
                        'exit_price': close[i],
                        'reason': 'SL Close Below Yearly R2 (Same Bar)',
                        'pnl_pct': round((close[i] - entry_price)/entry_price * 100, 2)
                    })
                    state = "IDLE"
                    continue
            else:
                # Next candle failed to break high -> reset to IDLE
                state = "IDLE"
                # Re-evaluate candle i for fresh qualification
                fresh_mr3 = (close[i] > mr3[i]) and (np.isnan(mr3[i-1]) or close[i-1] <= mr3[i-1])
                above_yr2 = close[i] > yr2[i]
                if fresh_mr3 and above_yr2:
                    qualifying_high = high[i]
                    state = "AWAITING_BREAKOUT"
                    continue
                    
        elif state == "IN_TRADE":
            # 1. Target Profit check (+40%)
            if high[i] >= tp_price:
                exit_price = max(open_[i], tp_price)
                trades.append({
                    'sym': sym,
                    'entry_date': dates[trade_entry_idx],
                    'entry_price': entry_price,
                    'exit_date': dates[i],
                    'exit_price': exit_price,
                    'reason': 'TP 40%',
                    'pnl_pct': round((exit_price - entry_price)/entry_price * 100, 2)
                })
                state = "IDLE"
                continue
            # 2. Stop Loss check: Daily candle close below Yearly R2
            elif close[i] < yr2[i]:
                trades.append({
                    'sym': sym,
                    'entry_date': dates[trade_entry_idx],
                    'entry_price': entry_price,
                    'exit_date': dates[i],
                    'exit_price': close[i],
                    'reason': 'SL Close Below Yearly R2',
                    'pnl_pct': round((close[i] - entry_price)/entry_price * 100, 2)
                })
                state = "IDLE"
                continue

    if trades:
        total_trades += len(trades)
        for t in trades:
            print(f"{t['sym']:<12} | Entry: {t['entry_date']} @ {t['entry_price']:<8.2f} | Exit: {t['exit_date']} @ {t['exit_price']:<8.2f} | {t['pnl_pct']:>6.2f}% | {t['reason']}")

print(f"\nTotal trades across sample: {total_trades}")

import pandas as pd
import numpy as np
import os

def compute_yearly_pivot_r1(df: pd.DataFrame):
    if 'date' in df.columns:
        year_period = pd.to_datetime(df['date']).dt.to_period('Y')
    elif isinstance(df.index, pd.DatetimeIndex):
        year_period = df.index.to_period('Y')
    else:
        year_period = pd.to_datetime(df.index).to_period('Y')

    yearly_ohlc = pd.DataFrame({
        'high': df['high'], 'low': df['low'], 'close': df['close'],
    }, index=df.index).groupby(year_period).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))

    yearly_pivot = (yearly_ohlc['high'] + yearly_ohlc['low'] + yearly_ohlc['close']) / 3.0
    yearly_r1 = 2.0 * yearly_pivot - yearly_ohlc['low']

    pivot_for_row = year_period.map(yearly_pivot.shift(1)).to_numpy(dtype=float)
    r1_for_row = year_period.map(yearly_r1.shift(1)).to_numpy(dtype=float)
    return pivot_for_row, r1_for_row

def ensure_weekly_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if 'date' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df['date'])
    elif 'Date' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df['Date'])
    
    clean_cols = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow in ['open', 'high', 'low', 'close', 'volume', 'date', 'market_cap_cr', 'symbol'] and clow not in clean_cols.values():
            clean_cols[c] = clow
    df_clean = df[list(clean_cols.keys())].rename(columns=clean_cols)
    
    if len(df_clean) > 5:
        median_spacing = pd.Series(df_clean.index).diff().median()
        if median_spacing >= pd.Timedelta(days=5):
            return df_clean

    agg_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    if 'market_cap_cr' in df_clean.columns:
        agg_dict['market_cap_cr'] = 'last'
    if 'symbol' in df_clean.columns:
        agg_dict['symbol'] = 'last'

    w_df = df_clean.resample('W-FRI').agg(agg_dict).dropna(subset=['close'])
    w_df['date'] = w_df.index.strftime('%Y-%m-%d')
    w_df['Date'] = w_df['date']
    return w_df

def volume_confirmed(volume: np.ndarray, i: int, lookback: int = 52) -> bool:
    start = max(0, i - lookback)
    if start >= i:
        return False
    window = volume[start:i]
    return volume[i] > window.max()

def simulate_tweaked_strategy(df: pd.DataFrame, tp_pct: float = 50.0, ema_period: int = 10, max_wait_bars: int = 15):
    w_df = ensure_weekly_df(df)
    n = len(w_df)
    if n < 55:
        return [], w_df

    high = w_df['high'].to_numpy(dtype=float)
    low = w_df['low'].to_numpy(dtype=float)
    close = w_df['close'].to_numpy(dtype=float)
    volume = w_df['volume'].to_numpy(dtype=float)
    dates = w_df['date'].astype(str).to_numpy()

    _, r1 = compute_yearly_pivot_r1(w_df)
    ema = pd.Series(close).ewm(span=ema_period, adjust=False).mean().to_numpy()

    trades = []
    
    # State variables:
    # state: 'IDLE', 'IN_TRADE', 'WAITING_FOR_REENTRY'
    state = 'IDLE'
    initial_buy_idx = None
    tracking_deadline_idx = None
    trade_entry_idx = None
    entry_price = None
    tp_price = None
    trade_type = None # 'INITIAL' or 'REENTRY'
    
    i = 1
    while i < n:
        if np.isnan(r1[i]):
            i += 1
            continue

        if state == 'IDLE':
            # Check Initial Buy condition:
            # High crosses above Yearly R1 + Volume confirmation
            crossed_now = high[i] > r1[i]
            was_below = high[i - 1] <= r1[i - 1] if not np.isnan(r1[i - 1]) else False
            vol_ok = volume_confirmed(volume, i)

            if crossed_now and was_below and vol_ok:
                initial_buy_idx = i
                tracking_deadline_idx = i + max_wait_bars
                trade_entry_idx = i
                entry_price = high[i] # breakout high
                tp_price = entry_price * (1.0 + tp_pct / 100.0)
                trade_type = 'INITIAL'
                state = 'IN_TRADE'
                # Entry candle itself: check if TP hit intrabar?
                # (usually rare on entry candle, but check)
                if high[i] >= tp_price:
                    trades.append({
                        'type': trade_type,
                        'entry_date': dates[i],
                        'entry_price': round(entry_price, 2),
                        'exit_date': dates[i],
                        'exit_price': round(tp_price, 2),
                        'exit_reason': 'TP (Same Bar)',
                        'pnl_pct': round(tp_pct, 2)
                    })
                    state = 'IDLE'
                i += 1
                continue

        elif state == 'IN_TRADE':
            bars_in_trade = i - trade_entry_idx
            
            # Check Early Exit in the next immediate two candles (bars 1 and 2):
            if bars_in_trade in (1, 2):
                # 1. Target Profit check
                if high[i] >= tp_price:
                    pnl = (tp_price - entry_price) / entry_price * 100.0
                    trades.append({
                        'type': trade_type,
                        'entry_date': dates[trade_entry_idx],
                        'entry_price': round(entry_price, 2),
                        'exit_date': dates[i],
                        'exit_price': round(tp_price, 2),
                        'exit_reason': 'TP',
                        'pnl_pct': round(pnl, 2)
                    })
                    # Trade hit TP, cycle completes
                    state = 'IDLE'
                    i += 1
                    continue

                # 2. Early Exit rule: if candle closes below R1
                if close[i] < r1[i]:
                    exit_price = close[i]
                    pnl = (exit_price - entry_price) / entry_price * 100.0
                    trades.append({
                        'type': trade_type,
                        'entry_date': dates[trade_entry_idx],
                        'entry_price': round(entry_price, 2),
                        'exit_date': dates[i],
                        'exit_price': round(exit_price, 2),
                        'exit_reason': f'Early Exit (Close Below Yearly R1 on bar {bars_in_trade})',
                        'pnl_pct': round(pnl, 2)
                    })
                    
                    # Switch to WAITING_FOR_REENTRY if within tracking deadline
                    if i < tracking_deadline_idx:
                        state = 'WAITING_FOR_REENTRY'
                    else:
                        state = 'IDLE'
                    i += 1
                    continue

            # If bar >= 3 or didn't close below R1 in bars 1 & 2:
            # Normal Trade Management:
            # Check TP
            if high[i] >= tp_price:
                pnl = (tp_price - entry_price) / entry_price * 100.0
                trades.append({
                    'type': trade_type,
                    'entry_date': dates[trade_entry_idx],
                    'entry_price': round(entry_price, 2),
                    'exit_date': dates[i],
                    'exit_price': round(tp_price, 2),
                    'exit_reason': 'TP',
                    'pnl_pct': round(pnl, 2)
                })
                state = 'IDLE'
                i += 1
                continue

            # Check Stop Loss: Close below 10 EMA
            if not np.isnan(ema[i]) and close[i] < ema[i]:
                exit_price = low[i]
                pnl = (exit_price - entry_price) / entry_price * 100.0
                trades.append({
                    'type': trade_type,
                    'entry_date': dates[trade_entry_idx],
                    'entry_price': round(entry_price, 2),
                    'exit_date': dates[i],
                    'exit_price': round(exit_price, 2),
                    'exit_reason': 'SL (Close Below 10 EMA)',
                    'pnl_pct': round(pnl, 2)
                })
                # Normal trade exit -> cycle complete
                state = 'IDLE'
                i += 1
                continue

        elif state == 'WAITING_FOR_REENTRY':
            # We are waiting for a candle to close above R1 again
            # Without volume confirmation
            # Must be within 15 candles from initial buy candle: i <= tracking_deadline_idx
            if i > tracking_deadline_idx:
                # 15 candles done -> drop tracking
                state = 'IDLE'
                # Note: i will now be evaluated as IDLE
                continue

            if close[i] > r1[i]:
                # Re-entry signal!
                trade_entry_idx = i
                entry_price = close[i] # or high[i]
                tp_price = entry_price * (1.0 + tp_pct / 100.0)
                trade_type = 'REENTRY'
                state = 'IN_TRADE'
                i += 1
                continue

        i += 1

    return trades, w_df

df_mayur = pd.read_parquet('data/adjusted_daily/MAYURUNIQ.parquet')
trades, w_df = simulate_tweaked_strategy(df_mayur)
print('MAYURUNIQ Trades with Tweaked Strategy:')
for t in trades:
    print(t)

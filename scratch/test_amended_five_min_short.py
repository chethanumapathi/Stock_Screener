import os
import glob
import pandas as pd
import numpy as np
from datetime import time as dtime

def compute_rsi(series: pd.Series, period: int = 14) -> np.ndarray:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(avg_gain != 0, 0.0)
    return rsi.fillna(50.0).to_numpy(dtype=float)

def compute_daily_r3(df: pd.DataFrame) -> np.ndarray:
    day_series = df.index.normalize()
    d_ohlc = df.groupby(day_series).agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    )
    pivot = (d_ohlc['high'] + d_ohlc['low'] + d_ohlc['close']) / 3.0
    r3 = d_ohlc['high'] + 2.0 * (pivot - d_ohlc['low'])
    r3_shifted = r3.shift(1)
    return day_series.map(r3_shifted).to_numpy(dtype=float)

def compute_daily_260_ema(df: pd.DataFrame, period: int = 260) -> np.ndarray:
    day_series = df.index.normalize()
    d_close = df.groupby(day_series)['close'].last()
    if len(d_close) >= period:
        d_ema = d_close.ewm(span=period, adjust=False).mean()
    else:
        d_ema = d_close.ewm(span=max(10, min(period, len(d_close))), adjust=False).mean()
    d_ema_shifted = d_ema.shift(1)
    return day_series.map(d_ema_shifted).to_numpy(dtype=float)

def compute_intraday_vwap(df: pd.DataFrame) -> np.ndarray:
    day_series = df.index.normalize()
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    pv = tp * df['volume']
    
    # Cumulative per day
    cum_pv = pv.groupby(day_series).cumsum()
    cum_vol = df['volume'].groupby(day_series).cumsum()
    vwap = cum_pv / cum_vol.replace(0, np.nan)
    return vwap.to_numpy(dtype=float)

def run_simulation(df_1m: pd.DataFrame, use_daily_260_ema: bool = True):
    if 'date' in df_1m.columns and not isinstance(df_1m.index, pd.DatetimeIndex):
        df_1m.index = pd.to_datetime(df_1m['date'])
    df_1m = df_1m.sort_index()
    
    agg_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    df_5m = df_1m.resample('5min', closed='left', label='left').agg(agg_dict).dropna(subset=['close']).copy()
    
    rsi_5m = compute_rsi(df_5m['close'], 14)
    r3_5m = compute_daily_r3(df_5m)
    ema260_5m = compute_daily_260_ema(df_5m, 260)
    
    c_rsi = rsi_5m > 85.0
    c_r3 = df_5m['close'].to_numpy() > r3_5m
    c_ema = (not use_daily_260_ema) | (df_5m['close'].to_numpy() < ema260_5m)
    
    prev_rsi = np.roll(c_rsi, 1)
    prev_rsi[0] = False
    prev_r3 = np.roll(c_r3, 1)
    prev_r3[0] = False
    
    qual_5m = (c_rsi & c_r3 & c_ema) & ~(prev_rsi & prev_r3)
    qual_5m_times = set(df_5m.index[qual_5m])
    
    vwap_1m = compute_intraday_vwap(df_1m)
    
    n = len(df_1m)
    open_1m = df_1m['open'].to_numpy(dtype=float)
    high_1m = df_1m['high'].to_numpy(dtype=float)
    low_1m = df_1m['low'].to_numpy(dtype=float)
    close_1m = df_1m['close'].to_numpy(dtype=float)
    dates_1m = df_1m.index.astype(str).to_numpy()
    times_1m = df_1m.index.time
    days_1m = df_1m.index.normalize()
    
    qual_5m_close_times = set([t + pd.Timedelta(minutes=5) for t in qual_5m_times])
    
    state = "IDLE"
    armed_day = None
    armed_1m_low = None
    day_high_so_far = 0.0
    
    trade_entry_idx = None
    entry_price = None
    tp_price = None
    sl_price = None
    mae = 0.0
    mfe = 0.0
    trades = []
    traded_days = set()
    
    TP_PCT = 2.0
    ENTRY_CUTOFF = dtime(13, 0)
    SQUARE_OFF = dtime(15, 15)
    
    for i in range(n):
        curr_t = df_1m.index[i]
        curr_tod = times_1m[i]
        curr_day = days_1m[i]
        
        if i == 0 or curr_day != days_1m[i - 1]:
            day_high_so_far = high_1m[i]
            if state != "IN_TRADE":
                state = "IDLE"
                armed_day = None
                armed_1m_low = None
        else:
            day_high_so_far = max(day_high_so_far, high_1m[i])
            
        is_cutoff = curr_tod > ENTRY_CUTOFF
        is_eod = curr_tod >= SQUARE_OFF
        
        if curr_t in qual_5m_close_times and state == "IDLE":
            if curr_day not in traded_days and not is_cutoff:
                state = "ARMED_5M"
                armed_day = curr_day
                armed_1m_low = None
        
        if state == "IN_TRADE":
            mae = max(mae, (high_1m[i] - entry_price) / entry_price * 100.0)
            mfe = max(mfe, (entry_price - low_1m[i]) / entry_price * 100.0)
            
            if high_1m[i] >= sl_price:
                exit_p = sl_price if open_1m[i] <= sl_price else open_1m[i]
                trades.append({
                    "entry_date": dates_1m[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates_1m[i],
                    "exit_price": round(float(exit_p), 2),
                    "exit_reason": "Stop Loss (Day High Breached)",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False
                })
                state = "IDLE"
                continue
            elif low_1m[i] <= tp_price:
                exit_p = tp_price if open_1m[i] >= tp_price else open_1m[i]
                trades.append({
                    "entry_date": dates_1m[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates_1m[i],
                    "exit_price": round(float(exit_p), 2),
                    "exit_reason": "Target Profit (2%)",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False
                })
                state = "IDLE"
                continue
            elif is_eod or (i + 1 < n and days_1m[i + 1] != curr_day):
                trades.append({
                    "entry_date": dates_1m[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates_1m[i],
                    "exit_price": round(float(close_1m[i]), 2),
                    "exit_reason": "EOD Square-off (15:15)",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False
                })
                state = "IDLE"
                continue
            continue
            
        if state == "ARMED_5M":
            if is_cutoff or curr_day != armed_day:
                state = "IDLE"
                continue
                
            cur_vwap = vwap_1m[i]
            if not np.isnan(cur_vwap) and close_1m[i] < cur_vwap:
                armed_1m_low = low_1m[i]
                state = "AWAITING_BREAK_OF_1M_LOW"
            continue
            
        if state == "AWAITING_BREAK_OF_1M_LOW":
            if is_cutoff or curr_day != armed_day:
                state = "IDLE"
                continue
                
            if low_1m[i] < armed_1m_low:
                entry_price = armed_1m_low if open_1m[i] >= armed_1m_low else open_1m[i]
                trade_entry_idx = i
                tp_price = entry_price * (1.0 - TP_PCT / 100.0)
                sl_price = day_high_so_far
                state = "IN_TRADE"
                mae = 0.0
                mfe = 0.0
                traded_days.add(curr_day)
                
                if high_1m[i] >= sl_price:
                    exit_p = sl_price if open_1m[i] <= sl_price else open_1m[i]
                    trades.append({
                        "entry_date": dates_1m[i],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates_1m[i],
                        "exit_price": round(float(exit_p), 2),
                        "exit_reason": "Stop Loss (Day High Breached Same Bar)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False
                    })
                    state = "IDLE"
                elif low_1m[i] <= tp_price:
                    exit_p = tp_price if open_1m[i] >= tp_price else open_1m[i]
                    trades.append({
                        "entry_date": dates_1m[i],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates_1m[i],
                        "exit_price": round(float(exit_p), 2),
                        "exit_reason": "Target Profit (2% Same Bar)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False
                    })
                    state = "IDLE"
                continue
            else:
                cur_vwap = vwap_1m[i]
                if not np.isnan(cur_vwap) and close_1m[i] < cur_vwap:
                    armed_1m_low = min(armed_1m_low, low_1m[i])
                    
    return trades, qual_5m_times

if __name__ == '__main__':
    all_trades = []
    files = glob.glob(r'C:\Zerodha Historical Data\data\minute\*.parquet')
    print(f'Scanning {len(files)} stocks for trade execution...')
    scanned = 0
    symbols_with_trades = []
    for f in files[:80]:
        sym = os.path.splitext(os.path.basename(f))[0]
        try:
            df = pd.read_parquet(f)
            trades, q_times = run_simulation(df, use_daily_260_ema=True)
            scanned += 1
            if trades:
                symbols_with_trades.append(sym)
                all_trades.extend(trades)
                print(f'{sym}: {len(trades)} trades, {len(q_times)} 5m qualifying events')
                for tr in trades[:2]:
                    print('  Trade:', tr)
        except Exception as e:
            pass
    print(f'Done scanning {scanned} stocks. Total trades: {len(all_trades)} across {len(symbols_with_trades)} symbols.')

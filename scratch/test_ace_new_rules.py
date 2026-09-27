import sys
sys.path.append('.')
import pandas as pd
import numpy as np

def run_simulation(df: pd.DataFrame):
    if 'date' in df.columns:
        df['dt'] = pd.to_datetime(df['date'])
    else:
        df['dt'] = pd.to_datetime(df.index)
    df = df.sort_values('dt').copy()
    df.index = df['dt']

    # 1. Yearly Pivots (Prior completed year)
    y_period = df['dt'].dt.to_period('Y')
    y_ohlc = df.groupby(y_period).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    y_pp = (y_ohlc['high'] + y_ohlc['low'] + y_ohlc['close']) / 3.0
    y_r2 = y_pp + (y_ohlc['high'] - y_ohlc['low'])
    yearly_r2 = y_period.map(y_r2.shift(1)).to_numpy(dtype=float)

    # 2. Monthly Pivots (Prior completed month): PP + 2*(High - Low)
    m_period = df['dt'].dt.to_period('M')
    m_ohlc = df.groupby(m_period).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    m_pp = (m_ohlc['high'] + m_ohlc['low'] + m_ohlc['close']) / 3.0
    m_r3 = m_pp + 2.0 * (m_ohlc['high'] - m_ohlc['low'])
    monthly_r3 = m_period.map(m_r3.shift(1)).to_numpy(dtype=float)

    # 3. Weekly Candles & 30 EMA
    w_df = df.resample('W-FRI').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna(subset=['close'])
    w_df['w_ema30'] = w_df['close'].ewm(span=30, adjust=False).mean()
    w_close = w_df['close'].to_numpy(dtype=float)
    w_low = w_df['low'].to_numpy(dtype=float)
    w_ema30 = w_df['w_ema30'].to_numpy(dtype=float)
    w_indices = w_df.index

    # Daily arrays
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)
    dates = df['dt'].dt.strftime('%Y-%m-%d').to_numpy()
    d_indices = df.index
    n = len(close)

    TP_PCT = 40.0
    state = "IDLE"
    qualifying_high = None
    qualifying_idx = None
    trade_entry_idx = None
    entry_price = None
    tp_price = None
    armed_sl_low = None
    last_checked_w_idx = -1
    trades = []

    i = 1
    while i < n:
        cur_date = d_indices[i]

        if state == "IN_TRADE":
            # Check completed weekly bars up to today
            w_past = np.where(w_indices < cur_date.floor('D'))[0]
            if len(w_past) > 0:
                cur_w_idx = w_past[-1]
                if cur_w_idx > last_checked_w_idx and cur_w_idx >= 0:
                    if w_close[cur_w_idx] < w_ema30[cur_w_idx]:
                        armed_sl_low = w_low[cur_w_idx] if armed_sl_low is None else min(armed_sl_low, w_low[cur_w_idx])
                    else:
                        armed_sl_low = None
                    last_checked_w_idx = cur_w_idx

            # 1. Target Profit (+40%)
            if high[i] >= tp_price:
                exit_p = tp_price if open_[i] <= tp_price else open_[i]
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(entry_price, 2),
                    "exit_date": dates[i],
                    "exit_price": round(exit_p, 2),
                    "exit_reason": f"Target Profit ({int(TP_PCT)}%)",
                    "pnl_pct": round((exit_p - entry_price) / entry_price * 100.0, 2),
                    "is_open": False
                })
                state = "IDLE"
                armed_sl_low = None
                i += 1
                continue

            # 2. Stop Loss (Weekly close below 30 EMA and low broken)
            if armed_sl_low is not None and low[i] < armed_sl_low:
                exit_p = armed_sl_low if open_[i] >= armed_sl_low else open_[i]
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(entry_price, 2),
                    "exit_date": dates[i],
                    "exit_price": round(exit_p, 2),
                    "exit_reason": "Stop Loss (Weekly Close Below 30 EMA and Low Broken)",
                    "pnl_pct": round((exit_p - entry_price) / entry_price * 100.0, 2),
                    "is_open": False
                })
                state = "IDLE"
                armed_sl_low = None
                i += 1
                continue

            i += 1
            continue

        if state == "IDLE":
            if np.isnan(monthly_r3[i]) or np.isnan(yearly_r2[i]):
                i += 1
                continue

            fresh_mr3 = (close[i] > monthly_r3[i]) and (np.isnan(monthly_r3[i - 1]) or close[i - 1] <= monthly_r3[i - 1])
            above_yr2 = close[i] > yearly_r2[i]

            if fresh_mr3 and above_yr2:
                qualifying_high = high[i]
                qualifying_idx = i
                state = "AWAITING_BREAKOUT"
            i += 1
            continue

        elif state == "AWAITING_BREAKOUT":
            if high[i] > qualifying_high:
                trade_entry_idx = i
                entry_price = qualifying_high if open_[i] <= qualifying_high else open_[i]
                tp_price = entry_price * (1.0 + TP_PCT / 100.0)
                state = "IN_TRADE"
                armed_sl_low = None
                last_checked_w_idx = -1

                # Check intrabar TP on entry day
                if high[i] >= tp_price:
                    exit_p = tp_price if open_[i] <= tp_price else open_[i]
                    trades.append({
                        "entry_date": dates[i],
                        "entry_price": round(entry_price, 2),
                        "exit_date": dates[i],
                        "exit_price": round(exit_p, 2),
                        "exit_reason": f"Target Profit ({int(TP_PCT)}% Same Bar)",
                        "pnl_pct": round((exit_p - entry_price) / entry_price * 100.0, 2),
                        "is_open": False
                    })
                    state = "IDLE"
                i += 1
                continue
            else:
                # Next day failed to break
                state = "IDLE"
                # Re-evaluate candle i for potential fresh breakout
                continue

    return trades

df = pd.read_parquet('data/adjusted_daily/ACE.parquet')
trades = run_simulation(df)
print("Simulation Trades for ACE:")
for t in trades:
    print(" ", t)

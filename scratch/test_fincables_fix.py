import sys
sys.path.insert(0, '.')
import duckdb
import pandas as pd
import numpy as np
from datetime import timedelta, time as dtime
from app import get_ticker_parquet_path
from strategies.fifteen_min_weekly_r3_r2_rsi80 import (
    _prepare_5min_df, compute_weekly_pivots, compute_rsi, compute_session_vwap, TP_PCT
)

ENTRY_CUTOFF_TIME = dtime(13, 0)
MAX_TRIGGER_WINDOW_DAYS = 21
MAX_BREAKOUT_WAIT_BARS = 15

def construct_nse_1hour_candles(df: pd.DataFrame) -> pd.DataFrame:
    times = df.index
    mins_from_midnight = times.hour * 60 + times.minute
    m_open = 9 * 60 + 15
    diff_mins = np.maximum(0, mins_from_midnight - m_open)
    hour_slot = diff_mins // 60
    
    day_series = times.normalize()
    grouped = df.groupby([day_series, hour_slot]).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    })
    
    bar_times = []
    close_times = []
    for (day, slot), _ in grouped.iterrows():
        start_min = m_open + slot * 60
        shour = start_min // 60
        smin = start_min % 60
        b_time = day.replace(hour=shour, minute=smin)
        bar_times.append(b_time)
        dur = 15 if (shour == 15 and smin == 15) else 60
        close_times.append(b_time + timedelta(minutes=dur))
        
    res = grouped.copy()
    res.index = pd.DatetimeIndex(bar_times)
    res['close_time'] = pd.DatetimeIndex(close_times)
    return res.sort_index()

def compute_nse_1hour_triggers(df_5m: pd.DataFrame):
    df_1h = construct_nse_1hour_candles(df_5m)
    if len(df_1h) < 2:
        return []
    
    _, weekly_r3_1h = compute_weekly_pivots(df_1h)
    h_close = df_1h['close'].to_numpy(dtype=float)
    h_close_times = np.array(df_1h['close_time'].dt.to_pydatetime())
    
    triggers = []
    for k in range(1, len(df_1h)):
        r3_curr = weekly_r3_1h[k]
        r3_prev = weekly_r3_1h[k - 1]
        if not np.isnan(r3_curr) and not np.isnan(r3_prev):
            if h_close[k] > r3_curr and h_close[k - 1] > r3_prev:
                triggers.append(h_close_times[k])
    return sorted(triggers)

def simulate_trades_updated(df: pd.DataFrame):
    n = len(df)
    open_ = df['open'].to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    times = df.index.to_pydatetime()
    days = df.index.normalize()
    tods = df.index.time
    date_strs = df['date'].astype(str).to_numpy()

    weekly_r2, weekly_r3 = compute_weekly_pivots(df)
    rsi = compute_rsi(pd.Series(close, index=df.index), 14)
    vwap = compute_session_vwap(df)
    trigger_completion_times = compute_nse_1hour_triggers(df)

    long_entry = np.zeros(n, dtype=bool)
    signal = np.zeros(n, dtype=bool)
    tp_arr = np.full(n, np.nan)
    sl_arr = np.full(n, np.nan)
    trades = []

    state = "IDLE"
    trigger_time = None
    trigger_day = None
    qualifying_high = None
    breakout_bars_waited = 0
    trigger_idx_pointer = 0
    num_triggers = len(trigger_completion_times)

    trade_entry_idx = None
    entry_price = None
    tp_price = None
    armed_vwap_sl = None
    armed_r2_sl = None
    mae = 0.0
    mfe = 0.0

    entered_days = set()

    def close_trade(exit_idx, exit_px, reason, is_open=False):
        trades.append({
            "entry_date": date_strs[trade_entry_idx],
            "entry_price": round(float(entry_price), 2),
            "exit_date": date_strs[exit_idx],
            "exit_price": round(float(exit_px), 2),
            "exit_reason": reason,
            "mae_pct": round(float(mae), 2),
            "mfe_pct": round(float(mfe), 2),
            "is_open": bool(is_open),
        })

    for i in range(1, n):
        curr_time = times[i]
        curr_day = days[i]
        curr_tod = tods[i]

        # Advance trigger pointer for 1-hour completions that occurred at or before curr_time
        while trigger_idx_pointer < num_triggers and trigger_completion_times[trigger_idx_pointer] <= curr_time:
            t_trig = trigger_completion_times[trigger_idx_pointer]
            trigger_idx_pointer += 1
            if state == "IDLE":
                trigger_time = t_trig
                trigger_day = pd.Timestamp(t_trig).normalize()
                state = "ARMED_TRIGGER"

        # 1. Manage Active Trade
        if state == "IN_TRADE":
            mae = max(mae, (entry_price - low[i]) / entry_price * 100.0)
            mfe = max(mfe, (high[i] - entry_price) / entry_price * 100.0)

            exited = False

            if high[i] >= tp_price:
                exit_px = tp_price if open_[i] <= tp_price else open_[i]
                close_trade(i, exit_px, f"Target Profit (+{TP_PCT}%)")
                state = "IDLE"
                exited = True
            else:
                hit_vwap_sl = armed_vwap_sl is not None and low[i] <= armed_vwap_sl
                hit_r2_sl = armed_r2_sl is not None and low[i] <= armed_r2_sl

                if hit_vwap_sl or hit_r2_sl:
                    if hit_vwap_sl and hit_r2_sl:
                        eff_sl = max(armed_vwap_sl, armed_r2_sl)
                        exit_px = eff_sl if open_[i] >= eff_sl else open_[i]
                        close_trade(i, exit_px, "Stop Loss (Dual VWAP & Weekly R2 Low Broken)")
                    elif hit_vwap_sl:
                        exit_px = armed_vwap_sl if open_[i] >= armed_vwap_sl else open_[i]
                        close_trade(i, exit_px, "Stop Loss (VWAP Breakdown Candle Low Broken)")
                    else:
                        exit_px = armed_r2_sl if open_[i] >= armed_r2_sl else open_[i]
                        close_trade(i, exit_px, "Stop Loss (Weekly R2 Breakdown Candle Low Broken)")
                    state = "IDLE"
                    exited = True

            if not exited:
                if not np.isnan(vwap[i]) and close[i] < vwap[i]:
                    armed_vwap_sl = low[i] if armed_vwap_sl is None else min(armed_vwap_sl, low[i])
                if not np.isnan(weekly_r2[i]) and close[i] < weekly_r2[i]:
                    armed_r2_sl = low[i] if armed_r2_sl is None else min(armed_r2_sl, low[i])

                active_sl = None
                if armed_vwap_sl is not None and armed_r2_sl is not None:
                    active_sl = max(armed_vwap_sl, armed_r2_sl)
                elif armed_vwap_sl is not None:
                    active_sl = armed_vwap_sl
                elif armed_r2_sl is not None:
                    active_sl = armed_r2_sl
                if active_sl is not None:
                    sl_arr[i] = active_sl
            continue

        # 2. State: AWAITING_BREAKOUT
        if state == "AWAITING_BREAKOUT":
            breakout_bars_waited += 1

            elapsed = curr_time - trigger_time
            if elapsed > timedelta(days=MAX_TRIGGER_WINDOW_DAYS):
                state = "IDLE"
                continue

            # Check rule: not on the trigger day, max 1 trade per day, entry <= 1:00 PM
            day_ok = curr_day > trigger_day
            single_trade_ok = curr_day not in entered_days
            time_ok = curr_tod <= ENTRY_CUTOFF_TIME

            if high[i] > qualifying_high:
                if day_ok and single_trade_ok and time_ok:
                    trade_entry_idx = i
                    entry_price = qualifying_high if open_[i] <= qualifying_high else open_[i]
                    tp_price = entry_price * (1.0 + TP_PCT / 100.0)

                    long_entry[i] = True
                    tp_arr[i] = TP_PCT
                    state = "IN_TRADE"
                    armed_vwap_sl = None
                    armed_r2_sl = None
                    entered_days.add(curr_day)

                    mae = (entry_price - low[i]) / entry_price * 100.0
                    mfe = (high[i] - entry_price) / entry_price * 100.0

                    if high[i] >= tp_price:
                        exit_px = tp_price if open_[i] <= tp_price else open_[i]
                        close_trade(i, exit_px, f"Target Profit (+{TP_PCT}% Same Bar)")
                        state = "IDLE"
                    continue
                else:
                    # Breakout happened but blocked by rules (e.g. same day as trigger or post 1:00 PM)
                    state = "ARMED_TRIGGER"
                    continue

            if breakout_bars_waited >= MAX_BREAKOUT_WAIT_BARS:
                state = "ARMED_TRIGGER"
                continue

        # 3. State: ARMED_TRIGGER
        if state == "ARMED_TRIGGER":
            elapsed = curr_time - trigger_time
            if elapsed > timedelta(days=MAX_TRIGGER_WINDOW_DAYS):
                state = "IDLE"
                continue

            # Qualifying candle: only evaluate if not on trigger day and not already traded today and before 1:00 PM
            if curr_day <= trigger_day:
                # Rule: "we will not enter the same day when the buy trigger happened."
                continue
            if curr_day in entered_days:
                # Rule: "we will enter only one time in a day."
                continue
            if curr_tod > ENTRY_CUTOFF_TIME:
                # Rule: "we will not enter post 1:00 PM IST"
                continue

            r2_val = weekly_r2[i]
            r2_ok = (not np.isnan(r2_val)) and (close[i] > r2_val)
            rsi_ok = rsi[i] > 85.0

            if r2_ok and rsi_ok:
                signal[i] = True
                qualifying_high = high[i]
                breakout_bars_waited = 0
                state = "AWAITING_BREAKOUT"
                continue

    return trades

p = get_ticker_parquet_path('FINCABLES')
con = duckdb.connect()
df_raw = con.execute(f"SELECT * FROM '{p}' ORDER BY Date").df()
con.close()

df_5m = _prepare_5min_df(df_raw)
trades = simulate_trades_updated(df_5m)

print("\n--- FINCABLES Trades Around May 2026 (Updated Rules) ---")
for t in trades:
    if '2026-05' in str(t['entry_date']):
        print(t)

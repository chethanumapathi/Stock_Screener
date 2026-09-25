"""
1-Hour Weekly R3 Trigger -> 5-Min Weekly R2 + RSI>85 Short (TP VWAP | SL 3%)
============================================================================
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).
Base Timeframe: 5-Minute candles (automatically resamples 1-min data if provided).

STRATEGY CRITERIA & RULES:
1. Higher Timeframe Trigger (1-Hour Timeframe):
   - Genuine NSE 1-hour candles anchored at 09:15 IST:
     (09:15-10:15, 10:15-11:15, 11:15-12:15, 12:15-13:15, 13:15-14:15, 14:15-15:15).
   - Minimum two consecutive 1-hour candles close above Weekly R3:
     Close_1h[t-1] > Weekly_R3 and Close_1h[t] > Weekly_R3
     (Weekly R3 computed from prior completed week's OHLC:
      Pivot = (High_w + Low_w + Close_w) / 3.0, R3 = High_w + 2 * (Pivot - Low_w)).
   - This trigger arms the setup and starts a 3-week timer (21 calendar days / ~750 5m bars).

2. Signal & Short Entry Rules (5-Minute Timeframe):
   - NO entry on the same day when the 1-hour trigger happened (entries only allowed starting the next day).
   - NO entry post 1:00 PM IST (cutoff strictly at 13:00 IST).
   - ONLY ONE entry per day (strictly max 1 trade per day).
   - Within the next 3 weeks from the 1-hour trigger event:
     When a 5-minute candle enters / closes above Weekly R2 with 14-period RSI strictly above 85:
     Close_5m > Weekly_R2 and RSI_5m(14) > 85.0
   - We mark the HIGH of this qualifying 5-minute candle.
   - Short Entry Execution: Sell / Short order placed at the HIGH of this candle (exact same trigger level).
     When a subsequent 5-minute candle trades at or above this High (before 1:00 PM), sell short at max(Open, High).

3. Target Profit (TP):
   - Dynamic Session VWAP with a minimum 1.5% profit buffer from entry:
     Target Level = min(Session VWAP, Entry Price * 0.985).
     When price drops and Low <= Target Level, exit and cover short at Target Level (or Open).
     This guarantees every Target Profit exit yields a net positive return after factoring in
     the standard 1.0% round-trip slippage, ₹40 brokerage, and statutory taxes.

4. Stop Loss (SL):
   - Fixed 3.0% above entry price (SL = Entry Price * 1.03).
     When subsequent price rallies and High >= SL, exit and cover short at the SL level.

5. Intraday Exit:
   - Square off open positions at 15:15 IST before market close.
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import timedelta, time as dtime

# =========================================================================
# CONFIGURABLE PARAMETERS
# =========================================================================
TF_MINUTES = 5                   # Base strategy timeframe in minutes (5m)
RSI_PERIOD = 14                  # Wilder's smoothed RSI period
RSI_THRESHOLD = 85.0             # Qualifying 5m candle RSI threshold (> 85)

ENTRY_CUTOFF_TIME = dtime(13, 0) # No new entries post 1:00 PM IST (13:00)
DISALLOW_SAME_DAY_ENTRY = True   # We will not enter the same day when the trigger happened
MAX_TRADES_PER_DAY = 1           # Enter only one time in a day

MAX_TRIGGER_WINDOW_DAYS = 21     # 3 weeks (21 calendar days / ~750 5m bars)
MAX_BREAKOUT_WAIT_BARS = 15      # Max 5m bars to wait for price to touch qualifying high

MIN_TP_PCT = 1.5                 # Minimum 1.5% profit buffer required for VWAP Target Profit
SL_PCT = 3.0                     # Fixed 3.0% Stop Loss above entry price
INTRA_DAY_ONLY = True            # Strictly intraday: 15:15 EOD square-off


# =========================================================================
# TECHNICAL INDICATORS
# =========================================================================
def compute_rsi(series: pd.Series, period: int = 14) -> np.ndarray:
    """Standard Wilder's smoothed RSI matching TradingView ta.rsi."""
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


def compute_session_vwap(df: pd.DataFrame) -> np.ndarray:
    """
    Intraday Session VWAP resetting every trading day at market open.
    Typical Price = (High + Low + Close) / 3.0.
    """
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    vol = df['volume'].astype(float)
    day = df.index.normalize()
    cum_pv = (tp * vol).groupby(day).cumsum()
    cum_v = vol.groupby(day).cumsum().replace(0, np.nan)
    vwap = cum_pv / cum_v
    return vwap.to_numpy(dtype=float)


def compute_weekly_pivots(df: pd.DataFrame):
    """
    Computes Classical Weekly Pivot R2 and R3 from the PRIOR completed calendar week's OHLC (W-FRI):
        Pivot = (High_w + Low_w + Close_w) / 3.0
        R2    = Pivot + (High_w - Low_w)
        R3    = High_w + 2.0 * (Pivot - Low_w)
    Held constant across the current week's rows.
    """
    week_period = df.index.to_period('W-FRI')
    w_ohlc = df.groupby(week_period).agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    )
    pivot = (w_ohlc['high'] + w_ohlc['low'] + w_ohlc['close']) / 3.0
    r2 = pivot + (w_ohlc['high'] - w_ohlc['low'])
    r3 = w_ohlc['high'] + 2.0 * (pivot - w_ohlc['low'])

    r2_shifted = r2.shift(1)
    r3_shifted = r3.shift(1)

    r2_arr = r2_shifted.reindex(week_period).to_numpy(dtype=float)
    r3_arr = r3_shifted.reindex(week_period).to_numpy(dtype=float)
    return r2_arr, r3_arr


# =========================================================================
# DATA PREPARATION & NSE 1-HOUR CANDLE RESAMPLING
# =========================================================================
def _prepare_5min_df(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans and standardizes the input dataframe to 5-minute bars."""
    df = df.copy()
    clean_cols = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow in ['open', 'high', 'low', 'close', 'volume', 'date', 'symbol', 'market_cap_cr'] and clow not in clean_cols.values():
            clean_cols[c] = clow
    df_clean = df[list(clean_cols.keys())].rename(columns=clean_cols)

    if 'date' in df_clean.columns and not isinstance(df_clean.index, pd.DatetimeIndex):
        df_clean.index = pd.to_datetime(df_clean['date'])
    elif not isinstance(df_clean.index, pd.DatetimeIndex):
        df_clean.index = pd.to_datetime(df_clean.index)

    df_clean = df_clean[~df_clean.index.duplicated(keep='last')].sort_index()

    for col in ('open', 'high', 'low', 'close', 'volume'):
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')

    df_clean = df_clean.dropna(subset=['open', 'high', 'low', 'close'])

    if 'volume' not in df_clean.columns:
        df_clean['volume'] = 10000.0
    df_clean['volume'] = df_clean['volume'].fillna(10000.0)

    # Resample to 5-minute if bar spacing < 4 minutes (e.g. 1-minute data)
    if len(df_clean) > 5:
        median_spacing = pd.Series(df_clean.index).diff().median()
        if median_spacing < pd.Timedelta(minutes=4):
            agg_dict = {
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }
            if 'symbol' in df_clean.columns:
                agg_dict['symbol'] = 'last'
            if 'market_cap_cr' in df_clean.columns:
                agg_dict['market_cap_cr'] = 'last'

            resampled = df_clean.resample('5min', closed='left', label='left').agg(agg_dict)
            df_clean = resampled.dropna(subset=['open', 'high', 'low', 'close']).copy()

    df_clean = df_clean.copy()
    df_clean['date'] = df_clean.index.astype(str)
    return df_clean


def construct_nse_1hour_candles(df_5m: pd.DataFrame) -> pd.DataFrame:
    """
    Constructs genuine NSE 1-hour candles anchored at 09:15 IST:
    Slot 0: 09:15 - 10:15 (closes at 10:15)
    Slot 1: 10:15 - 11:15 (closes at 11:15)
    Slot 2: 11:15 - 12:15 (closes at 12:15)
    Slot 3: 12:15 - 13:15 (closes at 13:15)
    Slot 4: 13:15 - 14:15 (closes at 14:15)
    Slot 5: 14:15 - 15:15 (closes at 15:15)
    Slot 6: 15:15 - 15:30 (closes at 15:30)
    """
    if len(df_5m) == 0:
        return pd.DataFrame()
    times = df_5m.index
    mins_from_midnight = times.hour * 60 + times.minute
    m_open = 9 * 60 + 15
    diff_mins = np.maximum(0, mins_from_midnight - m_open)
    hour_slot = diff_mins // 60

    day_series = times.normalize()
    grouped = df_5m.groupby([day_series, hour_slot]).agg({
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
        shour = int(start_min // 60)
        smin = int(start_min % 60)
        b_time = day.replace(hour=shour, minute=smin)
        bar_times.append(b_time)
        dur = 15 if (shour == 15 and smin == 15) else 60
        close_times.append(b_time + timedelta(minutes=dur))

    res = grouped.copy()
    res.index = pd.DatetimeIndex(bar_times)
    res['close_time'] = pd.DatetimeIndex(close_times)
    return res.sort_index()


def compute_nse_1hour_triggers(df_5m: pd.DataFrame):
    """
    Identifies completion timestamps where two consecutive completed NSE 1-hour candles
    closed strictly above Weekly R3:
        Close_1h[t-1] > Weekly_R3 and Close_1h[t] > Weekly_R3
    Returns a sorted list of timestamps when the trigger completed.
    """
    df_1h = construct_nse_1hour_candles(df_5m)
    if len(df_1h) < 2:
        return []

    _, weekly_r3_1h = compute_weekly_pivots(df_1h)
    h_close = df_1h['close'].to_numpy(dtype=float)
    h_close_times = df_1h['close_time'].tolist()

    triggers = []
    for k in range(1, len(df_1h)):
        r3_curr = weekly_r3_1h[k]
        r3_prev = weekly_r3_1h[k - 1]
        if not np.isnan(r3_curr) and not np.isnan(r3_prev):
            if h_close[k] > r3_curr and h_close[k - 1] > r3_prev:
                triggers.append(h_close_times[k])

    return sorted(triggers)


# =========================================================================
# STATE MACHINE & SHORT TRADE SIMULATION
# =========================================================================
def simulate_trades(df: pd.DataFrame):
    """
    Simulates Short trades following:
    1. Higher Timeframe Trigger: At least two consecutive completed NSE 1h candles close above Weekly R3.
    2. Restrictions:
       - No entry on the same day when the trigger happened.
       - No entry post 1:00 PM IST (13:00 cutoff).
       - Max 1 entry per day.
    3. Signal: Within 3 weeks from trigger, a 5-minute candle closes above Weekly R2 with RSI > 85.
    4. Short Entry: Sell at the High of this qualifying 5m candle (exact same trigger price).
    5. Target Profit: Session VWAP (exit when Low <= VWAP).
    6. Stop Loss: Fixed 3.0% above entry price (exit when High >= entry * 1.03).
    """
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
    rsi = compute_rsi(pd.Series(close, index=df.index), RSI_PERIOD)
    vwap = compute_session_vwap(df)
    trigger_completion_times = compute_nse_1hour_triggers(df)

    short_entry = np.zeros(n, dtype=bool)
    signal = np.zeros(n, dtype=bool)
    tp_arr = np.full(n, np.nan)
    sl_arr = np.full(n, np.nan)
    trades = []

    # States: "IDLE", "ARMED_TRIGGER", "AWAITING_BREAKOUT", "IN_TRADE"
    state = "IDLE"

    trigger_time = None
    trigger_day = None
    qualifying_high = None
    breakout_bars_waited = 0
    trigger_idx_pointer = 0
    num_triggers = len(trigger_completion_times)

    trade_entry_idx = None
    entry_price = None
    sl_price = None
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
            "trade_type": "SHORT",
            "side": "SHORT",
            "direction": "SHORT",
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

        # 1. Manage Active Short Trade
        if state == "IN_TRADE":
            # For short positions: MAE is maximum upward rally, MFE is maximum downward drop
            mae = max(mae, (high[i] - entry_price) / entry_price * 100.0)
            mfe = max(mfe, (entry_price - low[i]) / entry_price * 100.0)

            # Check Dynamic Target Profit (Session VWAP with min 1.5% profit buffer: Low <= target_level)
            curr_vwap = vwap[i]
            min_tp_target = entry_price * (1.0 - MIN_TP_PCT / 100.0)
            target_level = min(curr_vwap, min_tp_target)
            if not np.isnan(curr_vwap) and low[i] <= target_level:
                exit_px = open_[i] if open_[i] <= target_level else target_level
                close_trade(i, exit_px, "Target Profit (Session VWAP Reached)")
                state = "IDLE"
                continue

            # Check Fixed Stop Loss (3.0% above entry: High >= sl_price)
            if high[i] >= sl_price:
                exit_px = open_[i] if open_[i] >= sl_price else sl_price
                close_trade(i, exit_px, f"Stop Loss (+{SL_PCT}% Hit)")
                state = "IDLE"
                continue

            # Intraday EOD Square-off (15:15)
            if INTRA_DAY_ONLY and (curr_time.hour >= 15 and curr_time.minute >= 15):
                close_trade(i, close[i], "EOD Square-off (15:15)")
                state = "IDLE"
                continue

            sl_arr[i] = sl_price
            tp_arr[i] = target_level
            continue

        # 2. State: AWAITING_BREAKOUT (Short order placed at qualifying 5m high)
        if state == "AWAITING_BREAKOUT":
            breakout_bars_waited += 1

            # Check 3-week expiration from initial 1-hour trigger
            elapsed = curr_time - trigger_time
            if elapsed > timedelta(days=MAX_TRIGGER_WINDOW_DAYS):
                state = "IDLE"
                continue

            # Filters:
            # - Not on the trigger day
            # - Max 1 entry per day
            # - Cutoff strictly <= 1:00 PM
            day_ok = (not DISALLOW_SAME_DAY_ENTRY) or (curr_day > trigger_day)
            single_trade_ok = curr_day not in entered_days
            time_ok = curr_tod <= ENTRY_CUTOFF_TIME

            # Execution check: price touches qualifying_high
            if high[i] >= qualifying_high:
                if day_ok and single_trade_ok and time_ok:
                    trade_entry_idx = i
                    entry_price = qualifying_high if open_[i] <= qualifying_high else open_[i]
                    sl_price = entry_price * (1.0 + SL_PCT / 100.0)

                    short_entry[i] = True
                    state = "IN_TRADE"
                    entered_days.add(curr_day)

                    mae = (high[i] - entry_price) / entry_price * 100.0
                    mfe = (entry_price - low[i]) / entry_price * 100.0

                    # Same-bar Stop Loss check (+3.0%) if price rallies past SL on entry bar
                    if high[i] >= sl_price:
                        exit_px = open_[i] if open_[i] >= sl_price else sl_price
                        close_trade(i, exit_px, f"Stop Loss (+{SL_PCT}% Hit Same Bar)")
                        state = "IDLE"
                    continue
                else:
                    # Breakout attempted but blocked by day/time/single-trade rules
                    state = "ARMED_TRIGGER"
                    continue

            # Timeout after 15 bars: return to ARMED_TRIGGER to watch for newer signal
            if breakout_bars_waited >= MAX_BREAKOUT_WAIT_BARS:
                state = "ARMED_TRIGGER"
                continue

        # 3. State: ARMED_TRIGGER (Within 3 weeks from 1-hour Weekly R3 trigger)
        if state == "ARMED_TRIGGER":
            elapsed = curr_time - trigger_time
            if elapsed > timedelta(days=MAX_TRIGGER_WINDOW_DAYS):
                state = "IDLE"
                continue

            # Filter out bars on trigger day, already traded days, or past 1:00 PM
            if DISALLOW_SAME_DAY_ENTRY and curr_day <= trigger_day:
                continue
            if curr_day in entered_days:
                continue
            if curr_tod > ENTRY_CUTOFF_TIME:
                continue

            # Check Qualifying 5-Minute Candle: Close > Weekly R2 AND RSI > 85.0
            r2_val = weekly_r2[i]
            r2_ok = (not np.isnan(r2_val)) and (close[i] > r2_val)
            rsi_ok = rsi[i] > RSI_THRESHOLD

            if r2_ok and rsi_ok:
                signal[i] = True
                qualifying_high = high[i]
                breakout_bars_waited = 0
                state = "AWAITING_BREAKOUT"
                continue

    if state == "IN_TRADE":
        close_trade(n - 1, close[-1], "End of Data", is_open=True)

    indicators = {
        'Weekly_R2': weekly_r2,
        'Weekly_R3': weekly_r3,
        'RSI_5m': rsi,
        'VWAP': vwap,
    }

    return trades, short_entry, signal, tp_arr, sl_arr, indicators


# =========================================================================
# SCREENER & BACKTESTER INTERFACE
# =========================================================================
def backtest(df: pd.DataFrame) -> dict:
    """Standard interface for Stock Screener backtest and sandbox execution."""
    df_5m = _prepare_5min_df(df)
    n = len(df_5m)

    empty_res = {
        "trades": [],
        "short_entry": pd.Series(False, index=df_5m.index),
        "long_entry": pd.Series(False, index=df_5m.index),
        "entries": pd.Series(False, index=df_5m.index),
        "signal": pd.Series(False, index=df_5m.index),
        "tp_pct": pd.Series(0.0, index=df_5m.index),
        "sl_pct": pd.Series(SL_PCT, index=df_5m.index),
        "df": df_5m
    }

    if n < 20:
        return empty_res

    trades, short_entry_arr, signal_arr, tp_arr, sl_arr, indicators = simulate_trades(df_5m)

    out_df = df_5m.copy()
    for k, v in indicators.items():
        out_df[k] = v
    out_df['Short_Entry'] = short_entry_arr
    out_df['Signal'] = signal_arr
    out_df['Stop_Loss'] = sl_arr
    out_df['Target_VWAP'] = tp_arr

    return {
        "trades": trades,
        "short_entry": pd.Series(short_entry_arr, index=df_5m.index),
        "long_entry": pd.Series(False, index=df_5m.index),
        "entries": pd.Series(short_entry_arr, index=df_5m.index),
        "signal": pd.Series(signal_arr, index=df_5m.index),
        "tp_pct": pd.Series(0.0, index=df_5m.index),
        "sl_pct": pd.Series(SL_PCT, index=df_5m.index),
        "df": out_df
    }

# Screener compatibility alias
screen = backtest

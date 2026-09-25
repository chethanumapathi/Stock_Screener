"""
5-Min Daily R3 + RSI>85 Short (1m VWAP Breakdown | TP 2% | SL Day High | Daily 260 EMA)
======================================================================================
Base Timeframe: 5-MINUTE qualification + 1-MINUTE execution (or 5m fallback).

STRATEGY CRITERIA & RULES:

1. DAILY 260 EMA TREND FILTER:
   - Evaluated on the Daily timeframe (computed from prior completed daily closes):
       Daily_260_EMA = EMA(Close_daily, 260)
   - Filter Requirement:
       The 5-minute candle that initiates the setup must be strictly BELOW the Daily 260 EMA:
       Close_5m < Daily_260_EMA
       (Ensures we only short stocks in macro downtrends / below their 260-day EMA).

2. 5-MINUTE SHORT QUALIFYING SETUP:
   - Daily Pivot R3 computed from the PRIOR completed calendar day's OHLC:
       Daily Pivot = (High_d + Low_d + Close_d) / 3.0
       Daily R3    = High_d + 2.0 * (Daily Pivot - Low_d)
   - Wilder's 14-period smoothed RSI on 5-minute candles:
       RSI_5m > 85.0
   - Candle Breakout & Crossover:
       The 5-minute candle closes above Daily R3 (Close_5m > Daily R3) AND has RSI_5m > 85.0.
   - Setup Armed:
       Do NOT short right away. This 5-minute candle arms the 1-minute breakdown setup.

3. 1-MINUTE SHORT EXECUTION TRIGGER (VWAP Breakdown):
   - In 1-Minute timeframe, calculate the Intraday Session VWAP (resets at 09:15 IST):
       VWAP = sum(Typical Price * Volume) / sum(Volume)
   - Wait for a 1-minute candle to close below the VWAP:
       Close_1m < VWAP_1m
   - The LOW of this 1-minute candle becomes the armed breakdown level:
       Armed_1m_Low = Low_1m
   - When a subsequent 1-minute candle breaks below this low:
       Low_1m < Armed_1m_Low
   - Execute SHORT entry immediately at Armed_1m_Low (or Open_1m if gapped below).

4. TARGET PROFIT (TP - 2%):
   - Fixed 2.0% profit target below entry price:
       TP_Price = Entry_Price * (1.0 - 0.02) = Entry_Price * 0.98.
   - When subsequent price drops and touches or breaches TP_Price:
       Low <= TP_Price
   - Cover short at TP_Price (or Open if gapped below).
   - Exit Reason: "Target Profit (2%)".

5. STOP LOSS (SL - High of the Current Day):
   - Stop Loss is set to the HIGH of the current trading day recorded up to entry:
       SL_Price = Current_Day_High.
   - When subsequent price rallies and touches or breaches SL_Price:
       High >= SL_Price
   - Exit and cover short at SL_Price (or Open if gapped above).
   - Exit Reason: "Stop Loss (Current Day High Breached)".

6. INTRADAY SESSION RULES (NSE IST):
   - Entry cutoff at 13:00 IST (no new entries post 1:00 PM).
   - EOD Square-off at 15:15 IST for open intraday short positions.
   - Strictly max 1 trade per day.
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import timedelta, time as dtime

# =========================================================================
# CONFIGURABLE PARAMETERS
# =========================================================================
RSI_PERIOD = 14                  # Wilder's 14-period RSI
RSI_THRESHOLD = 85.0             # RSI threshold (> 85.0)
DAILY_EMA_PERIOD = 260           # Daily Trend Filter EMA (sell only if candle is below Daily 260 EMA)
USE_DAILY_EMA_FILTER = True      # Enable Daily 260 EMA filter
TP_PCT = 2.0                     # Target Profit % (2% profit on short)
DEFAULT_TP_PCT = 2.0             # Fallback display TP % for template UI
DEFAULT_SL_PCT = 2.0             # Fallback display SL % for template UI

MAX_TRADES_PER_DAY = 1           # Strictly 1 short trade per day
USE_INTRADAY_SESSION = True      # Enable NSE session constraints
ENTRY_CUTOFF_TIME = dtime(13, 0) # No new entries post 1:00 PM IST (13:00)
SQUARE_OFF_TIME = dtime(15, 15)  # EOD Square-off at 15:15 IST


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


def compute_daily_r3(df: pd.DataFrame) -> np.ndarray:
    """
    Computes Classical Daily Pivot R3 from the PRIOR completed calendar day's OHLC:
        Pivot = (High_d + Low_d + Close_d) / 3.0
        R3    = High_d + 2.0 * (Pivot - Low_d)
    Held constant across the current day's rows.
    """
    day_series = df.index.normalize()
    d_ohlc = df.groupby(day_series).agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    )
    pivot = (d_ohlc['high'] + d_ohlc['low'] + d_ohlc['close']) / 3.0
    r3 = d_ohlc['high'] + 2.0 * (pivot - d_ohlc['low'])

    # Lag by 1 completed day
    r3_shifted = r3.shift(1)
    r3_arr = day_series.map(r3_shifted).to_numpy(dtype=float)
    return r3_arr


def compute_daily_260_ema(df: pd.DataFrame, period: int = 260) -> np.ndarray:
    """
    Computes Daily EMA (e.g. 260-period) from the PRIOR completed calendar day's Close,
    mapped onto intraday rows.
    """
    day_series = df.index.normalize()
    d_close = df.groupby(day_series)['close'].last()

    if len(d_close) >= period:
        d_ema = d_close.ewm(span=period, adjust=False).mean()
    else:
        d_ema = d_close.ewm(span=max(10, min(period, len(d_close))), adjust=False).mean()

    # Shift by 1 day so today's intraday bars reference yesterday's completed 260 EMA
    d_ema_shifted = d_ema.shift(1)
    d_ema_arr = day_series.map(d_ema_shifted).to_numpy(dtype=float)
    return d_ema_arr


def compute_intraday_vwap(df: pd.DataFrame) -> np.ndarray:
    """Computes genuine intraday session VWAP resetting at each trading day's open (09:15)."""
    day_series = df.index.normalize()
    typical_price = (df['high'] + df['low'] + df['close']) / 3.0
    pv = typical_price * df['volume']

    cum_pv = pv.groupby(day_series).cumsum()
    cum_vol = df['volume'].groupby(day_series).cumsum()
    vwap = cum_pv / cum_vol.replace(0, np.nan)
    return vwap.to_numpy(dtype=float)


# =========================================================================
# DATA PREPARATION
# =========================================================================
def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
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
    df_clean['date'] = df_clean.index.astype(str)
    return df_clean


# =========================================================================
# SHORT TRADE SIMULATION (1m execution after 5m qualification)
# =========================================================================
def simulate_trades(df_input: pd.DataFrame):
    """
    Executes the amended short strategy:
    - 5m Setup: Candle closes above Daily R3, RSI > 85, Close < Daily 260 EMA.
    - Post-Setup Trigger: Wait for 1m candle to close below Intraday VWAP.
    - Entry: Short at the Low of this 1m candle (placed as sell stop, filled when broken).
    - TP: 2.0% fixed target profit.
    - SL: Current day's high (up to entry bar).
    - Square-off: 15:15 IST.
    """
    df_clean = _clean_df(df_input)
    n_raw = len(df_clean)
    if n_raw < 30:
        return [], np.zeros(n_raw, dtype=bool), np.zeros(n_raw, dtype=bool), np.full(n_raw, np.nan), np.full(n_raw, np.nan), {}

    # Check if raw data is 1-minute (or sub-5m) vs already 5-minute
    median_spacing = pd.Series(df_clean.index).diff().median()
    is_minute_data = (median_spacing is not None) and (median_spacing < pd.Timedelta(minutes=3))

    if is_minute_data:
        df_1m = df_clean.copy()
        agg_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        if 'symbol' in df_1m.columns: agg_dict['symbol'] = 'last'
        if 'market_cap_cr' in df_1m.columns: agg_dict['market_cap_cr'] = 'last'
        df_5m = df_1m.resample('5min', closed='left', label='left').agg(agg_dict).dropna(subset=['close']).copy()
    else:
        # If input is already 5-minute, treat df_clean as the execution base
        df_5m = df_clean.copy()
        df_1m = df_clean.copy()

    # 5m Technical Indicators
    rsi_5m = compute_rsi(df_5m['close'], RSI_PERIOD)
    r3_5m = compute_daily_r3(df_5m)
    ema260_5m = compute_daily_260_ema(df_5m, DAILY_EMA_PERIOD)

    c_rsi = rsi_5m > RSI_THRESHOLD
    c_r3 = df_5m['close'].to_numpy(dtype=float) > r3_5m
    c_ema = (not USE_DAILY_EMA_FILTER) | (df_5m['close'].to_numpy(dtype=float) < ema260_5m)

    prev_rsi = np.roll(c_rsi, 1)
    prev_rsi[0] = False
    prev_r3 = np.roll(c_r3, 1)
    prev_r3[0] = False

    # 5m Qualified Candle: newly closed above R3 with RSI > 85, below Daily 260 EMA
    qual_5m = (c_rsi & c_r3 & c_ema) & ~(prev_rsi & prev_r3)
    qual_5m_times = set(df_5m.index[qual_5m])

    # Each 5m bar [T, T+5m) completes at T+5m. Execution on 1m starts at or after T+5m.
    qual_5m_close_times = set([t + pd.Timedelta(minutes=5) for t in qual_5m_times])

    # 1m Execution Indicators
    vwap_1m = compute_intraday_vwap(df_1m)

    n_exec = len(df_1m)
    open_1m = df_1m['open'].to_numpy(dtype=float)
    high_1m = df_1m['high'].to_numpy(dtype=float)
    low_1m = df_1m['low'].to_numpy(dtype=float)
    close_1m = df_1m['close'].to_numpy(dtype=float)
    dates_1m = df_1m['date'].astype(str).to_numpy()
    times_1m = df_1m.index.time
    days_1m = df_1m.index.normalize()

    short_entry_exec = np.zeros(n_exec, dtype=bool)
    signal_exec = np.zeros(n_exec, dtype=bool)
    tp_arr = np.full(n_exec, np.nan)
    sl_arr = np.full(n_exec, np.nan)
    trades = []

    state = "IDLE"  # "IDLE", "ARMED_5M", "AWAITING_BREAK_OF_1M_LOW", "IN_TRADE"
    armed_day = None
    armed_1m_low = None
    day_high_so_far = 0.0

    trade_entry_idx = None
    entry_price = None
    tp_price = None
    sl_price = None
    mae = 0.0
    mfe = 0.0
    traded_days = set()

    for i in range(n_exec):
        curr_t = df_1m.index[i]
        curr_tod = times_1m[i]
        curr_day = days_1m[i]

        # Track day high
        if i == 0 or curr_day != days_1m[i - 1]:
            day_high_so_far = high_1m[i]
            if state != "IN_TRADE":
                state = "IDLE"
                armed_day = None
                armed_1m_low = None
        else:
            day_high_so_far = max(day_high_so_far, high_1m[i])

        time_ok = (not USE_INTRADAY_SESSION) or (curr_tod <= ENTRY_CUTOFF_TIME)
        is_eod = USE_INTRADAY_SESSION and (curr_tod >= SQUARE_OFF_TIME)

        # Session rollover for open trade
        if state == "IN_TRADE" and curr_day != days_1m[trade_entry_idx]:
            trades.append({
                "entry_date": dates_1m[trade_entry_idx],
                "entry_price": round(float(entry_price), 2),
                "exit_date": dates_1m[i - 1],
                "exit_price": round(float(close_1m[i - 1]), 2),
                "exit_reason": "EOD Square-off (Session Rollover)",
                "trade_type": "SHORT",
                "side": "SHORT",
                "direction": "SHORT",
                "mae_pct": round(float(mae), 2),
                "mfe_pct": round(float(mfe), 2),
                "is_open": False
            })
            state = "IDLE"

        # Check if a 5m qualification event just completed
        if curr_t in qual_5m_close_times and state == "IDLE":
            if curr_day not in traded_days and time_ok and not is_eod:
                state = "ARMED_5M"
                armed_day = curr_day
                armed_1m_low = None

        # ---------------------------------------------------------------------
        # 1. STATE: IN_TRADE (Manage Short Trade Exits)
        # ---------------------------------------------------------------------
        if state == "IN_TRADE":
            mfe = max(mfe, (entry_price - low_1m[i]) / entry_price * 100.0)
            mae = max(mae, (high_1m[i] - entry_price) / entry_price * 100.0)

            tp_arr[i] = tp_price
            sl_arr[i] = sl_price

            # Exit Check 1: Stop Loss (Current Day High Breached)
            if high_1m[i] >= sl_price:
                exit_p = sl_price if open_1m[i] <= sl_price else open_1m[i]
                trades.append({
                    "entry_date": dates_1m[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates_1m[i],
                    "exit_price": round(float(exit_p), 2),
                    "exit_reason": "Stop Loss (Current Day High Hit)",
                    "trade_type": "SHORT",
                    "side": "SHORT",
                    "direction": "SHORT",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False
                })
                state = "IDLE"
                continue

            # Exit Check 2: Target Profit (2% Gain on Short)
            elif low_1m[i] <= tp_price:
                exit_p = tp_price if open_1m[i] >= tp_price else open_1m[i]
                trades.append({
                    "entry_date": dates_1m[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates_1m[i],
                    "exit_price": round(float(exit_p), 2),
                    "exit_reason": "Target Profit (2%)",
                    "trade_type": "SHORT",
                    "side": "SHORT",
                    "direction": "SHORT",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False
                })
                state = "IDLE"
                continue

            # Exit Check 3: EOD Square-off at 15:15 IST
            elif is_eod or (i + 1 < n_exec and days_1m[i + 1] != curr_day):
                trades.append({
                    "entry_date": dates_1m[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates_1m[i],
                    "exit_price": round(float(close_1m[i]), 2),
                    "exit_reason": "EOD Square-off (15:15)",
                    "trade_type": "SHORT",
                    "side": "SHORT",
                    "direction": "SHORT",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False
                })
                state = "IDLE"
                continue

            continue

        # ---------------------------------------------------------------------
        # 2. STATE: ARMED_5M (Waiting for 1-minute close below VWAP)
        # ---------------------------------------------------------------------
        if state == "ARMED_5M":
            if not time_ok or is_eod or curr_day != armed_day:
                state = "IDLE"
                continue

            cur_vwap = vwap_1m[i]
            if not np.isnan(cur_vwap) and close_1m[i] < cur_vwap:
                # 1m candle closed below VWAP: arm its low as the short trigger level
                armed_1m_low = low_1m[i]
                signal_exec[i] = True
                state = "AWAITING_BREAK_OF_1M_LOW"
            continue

        # ---------------------------------------------------------------------
        # 3. STATE: AWAITING_BREAK_OF_1M_LOW (Short when candle breaks armed low)
        # ---------------------------------------------------------------------
        if state == "AWAITING_BREAK_OF_1M_LOW":
            if not time_ok or is_eod or curr_day != armed_day:
                state = "IDLE"
                continue

            # Check if this candle breaks below the armed 1m low
            if low_1m[i] < armed_1m_low:
                entry_price = armed_1m_low if open_1m[i] >= armed_1m_low else open_1m[i]
                trade_entry_idx = i
                short_entry_exec[i] = True
                tp_price = round(entry_price * (1.0 - TP_PCT / 100.0), 2)
                sl_price = round(day_high_so_far, 2)

                state = "IN_TRADE"
                mae = 0.0
                mfe = 0.0
                traded_days.add(curr_day)

                # Intrabar exit on entry bar itself
                if high_1m[i] >= sl_price:
                    exit_p = sl_price if open_1m[i] <= sl_price else open_1m[i]
                    trades.append({
                        "entry_date": dates_1m[i],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates_1m[i],
                        "exit_price": round(float(exit_p), 2),
                        "exit_reason": "Stop Loss (Current Day High Hit Same Bar)",
                        "trade_type": "SHORT",
                        "side": "SHORT",
                        "direction": "SHORT",
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
                        "trade_type": "SHORT",
                        "side": "SHORT",
                        "direction": "SHORT",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False
                    })
                    state = "IDLE"
                continue
            else:
                # If price closes below VWAP with a lower low, trail the armed low
                cur_vwap = vwap_1m[i]
                if not np.isnan(cur_vwap) and close_1m[i] < cur_vwap:
                    armed_1m_low = min(armed_1m_low, low_1m[i])

    if state == "IN_TRADE":
        trades.append({
            "entry_date": dates_1m[trade_entry_idx],
            "entry_price": round(float(entry_price), 2),
            "exit_date": dates_1m[-1],
            "exit_price": round(float(close_1m[-1]), 2),
            "exit_reason": "End of Data",
            "trade_type": "SHORT",
            "side": "SHORT",
            "direction": "SHORT",
            "mae_pct": round(float(mae), 2),
            "mfe_pct": round(float(mfe), 2),
            "is_open": True
        })

    # Indicators for diagnostics
    indicators = {
        'Daily_R3': compute_daily_r3(df_clean),
        'Daily_260_EMA': compute_daily_260_ema(df_clean, DAILY_EMA_PERIOD),
        'VWAP': compute_intraday_vwap(df_clean),
    }

    return trades, short_entry_exec, signal_exec, tp_arr, sl_arr, indicators, df_clean


# =========================================================================
# SCREENER & BACKTESTER INTERFACE (app.py compatible)
# =========================================================================
def backtest(df: pd.DataFrame) -> dict:
    """Standard interface for Stock Screener backtest and sandbox execution."""
    df_clean = _clean_df(df)
    n = len(df_clean)

    empty_res = {
        "trades": [],
        "short_entry": pd.Series(False, index=df_clean.index),
        "long_entry": pd.Series(False, index=df_clean.index),
        "entries": pd.Series(False, index=df_clean.index),
        "signal": pd.Series(False, index=df_clean.index),
        "tp_pct": pd.Series(DEFAULT_TP_PCT, index=df_clean.index),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=df_clean.index),
        "df": df_clean
    }

    if n < (DAILY_EMA_PERIOD // 5 + 30):
        return empty_res

    trades, short_entry_arr, signal_arr, tp_arr, sl_arr, indicators, out_df = simulate_trades(df_clean)

    for k, v in indicators.items():
        if len(v) == len(out_df):
            out_df[k] = v
    out_df['Short_Entry'] = short_entry_arr
    out_df['Signal'] = signal_arr
    out_df['Stop_Loss_Price'] = sl_arr
    out_df['Target_Profit_Price'] = tp_arr

    return {
        "trades": trades,
        "short_entry": pd.Series(short_entry_arr, index=out_df.index),
        "long_entry": pd.Series(short_entry_arr, index=out_df.index),  # Alias for UI widget compatibility
        "entries": pd.Series(short_entry_arr, index=out_df.index),
        "signal": pd.Series(signal_arr, index=out_df.index),
        "tp_pct": pd.Series(TP_PCT, index=out_df.index),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=out_df.index),
        "df": out_df
    }


# Screener compatibility alias
screen = backtest

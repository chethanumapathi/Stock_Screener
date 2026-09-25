"""
1-Hour Multi-Timeframe Strategy: Weekly R3 + Daily 200 EMA + Supertrend (7, 3) Pullback Sequence
==================================================================================================
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).
Base Timeframe: 1-Hour candles (automatically resamples 1-min, 5-min, or 15-min data if provided).

STRATEGY CRITERIA:
1. Timeframe (TF): 1-Hour (60-minute candles).
2. Trend Filter (Daily 200 EMA):
   - Prior to the buy trigger candle, the past 5 completed daily candles must close above Daily 200 EMA.
3. Buy Trigger:
   - A 1-hour candle closes above Weekly R3: Close_1h > Weekly_R3
4. Buy Signal & Entry:
   - Within the NEXT 2 WEEKS (14 calendar days / ~70 hourly bars) from the initial candle
     which crossed above Weekly R3:
     * Supertrend (7, 3) must first print a SELL signal (pullback), AND
     * Subsequently flip back to a BUY signal (reversal).
   - Entry Execution: Buy stop placed at the HIGH of this Supertrend Buy reversal candle.
     When a subsequent candle trades above this High, buy long at max(Open, High).
5. Target Profit (TP): Fixed +10.0% from the entry price.
6. Stop Loss (SL): Supertrend (7, 3) Sell Signal.
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import timedelta

# =========================================================================
# CONFIGURABLE PARAMETERS
# =========================================================================
TF_HOURS = 1                     # Base strategy timeframe in hours (1h)
SUPERTREND_PERIOD = 7            # Supertrend ATR period
SUPERTREND_MULTIPLIER = 3.0      # Supertrend ATR multiplier
DAILY_EMA_PERIOD = 200           # Daily Trend Filter EMA period

MAX_TRIGGER_WINDOW_DAYS = 14     # Next 2 weeks (14 calendar days / ~70 1h bars) from the initial Weekly R3 trigger candle
MAX_BREAKOUT_WAIT_BARS = 10      # Max 1h bars to wait for breakout above qualifying high

TP_PCT = 10.0                    # Fixed +10.0% Target Profit
DEFAULT_SL_PCT = 5.0             # Fallback display SL % for template UI
INTRA_DAY_ONLY = False           # Multi-day swing by default; set True to force 15:15 EOD square-off


# =========================================================================
# TECHNICAL INDICATORS
# =========================================================================
def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 7) -> np.ndarray:
    """Wilder's ATR (RMA smoothing of True Range) matching TradingView ta.atr."""
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hpc = abs(high[i] - close[i - 1])
        lpc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hpc, lpc)

    atr = pd.Series(tr).ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr.to_numpy(dtype=float)


def compute_supertrend(df: pd.DataFrame, period: int = 7, multiplier: float = 3.0):
    """
    Supertrend Indicator matching TradingView ta.supertrend(multiplier, period) exactly.
    Returns:
        supertrend (np.ndarray): Supertrend line
        direction (np.ndarray): +1 for Bullish (Buy), -1 for Bearish (Sell)
    """
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    n = len(close)

    atr = compute_atr(high, low, close, period)
    hl2 = (high + low) / 2.0

    basic_upper = hl2 + multiplier * atr  # dn
    basic_lower = hl2 - multiplier * atr  # up

    up = np.full(n, np.nan)
    dn = np.full(n, np.nan)
    direction = np.ones(n, dtype=int)
    supertrend = np.full(n, np.nan)

    initialized = False
    for i in range(n):
        if np.isnan(atr[i]):
            continue

        if not initialized:
            up[i] = basic_lower[i]
            dn[i] = basic_upper[i]
            direction[i] = 1 if close[i] >= up[i] else -1
            supertrend[i] = up[i] if direction[i] == 1 else dn[i]
            initialized = True
            continue

        up1 = up[i - 1]
        dn1 = dn[i - 1]

        # Calculate up (lower band)
        up[i] = max(basic_lower[i], up1) if close[i - 1] > up1 else basic_lower[i]

        # Calculate dn (upper band)
        dn[i] = min(basic_upper[i], dn1) if close[i - 1] < dn1 else basic_upper[i]

        # Determine trend direction
        prev_dir = direction[i - 1]
        if prev_dir == -1 and close[i] > dn1:
            direction[i] = 1
        elif prev_dir == 1 and close[i] < up1:
            direction[i] = -1
        else:
            direction[i] = prev_dir

        supertrend[i] = up[i] if direction[i] == 1 else dn[i]

    return supertrend, direction


def compute_weekly_pivot_r3(df: pd.DataFrame) -> np.ndarray:
    """
    Computes Classical Weekly Pivot R3 from the PRIOR completed calendar week's OHLC (W-FRI):
        Pivot = (High_w + Low_w + Close_w) / 3.0
        R3    = High_w + 2.0 * (Pivot - Low_w)
    Held constant across the current week's 1-hour rows.
    """
    week_period = df.index.to_period('W-FRI')
    w_ohlc = df.groupby(week_period).agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    )
    pivot = (w_ohlc['high'] + w_ohlc['low'] + w_ohlc['close']) / 3.0
    r3 = w_ohlc['high'] + 2.0 * (pivot - w_ohlc['low'])

    r3_shifted = r3.shift(1)
    return r3_shifted.reindex(week_period).to_numpy(dtype=float)


def compute_daily_200_ema_filter(df: pd.DataFrame, ema_period: int = 200):
    """
    Aggregates to Daily bars, computes 200 EMA on daily close.
    Evaluates condition: Prior 5 completed daily candles before the trigger candle
    must all have closed strictly above the Daily 200 EMA.
    Maps boolean mask back onto 1-hour rows.
    """
    day_period = df.index.to_period('D')
    d_close = df.groupby(day_period)['close'].last()

    if len(d_close) >= ema_period:
        d_ema = d_close.ewm(span=ema_period, adjust=False).mean()
    else:
        # If fewer than 200 days available, use available history
        d_ema = d_close.ewm(span=min(50, len(d_close)), adjust=False).mean()

    cond_daily = (d_close > d_ema).to_numpy(dtype=bool)
    past_5_above = np.zeros(len(cond_daily), dtype=bool)
    for idx in range(5, len(cond_daily)):
        # Strictly verify that all 5 prior daily candles (idx-5 to idx-1) closed above Daily 200 EMA
        past_5_above[idx] = bool(np.all(cond_daily[idx - 5 : idx]))

    cond_pass = pd.Series(past_5_above & cond_daily, index=day_period.drop_duplicates())

    return cond_pass.reindex(day_period).fillna(False).to_numpy(dtype=bool), d_ema.reindex(day_period).to_numpy(dtype=float)


# =========================================================================
# DATA PREPARATION & RESAMPLING
# =========================================================================
def _prepare_1hour_df(df: pd.DataFrame) -> pd.DataFrame:
    """Standardizes input dataframe to 1-hour bars."""
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

    # Resample to 1-hour if bar spacing < 55 minutes
    if len(df_clean) > 5:
        median_spacing = pd.Series(df_clean.index).diff().median()
        if median_spacing < pd.Timedelta(minutes=55):
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

            resampled = df_clean.resample('1h', closed='left', label='left').agg(agg_dict)
            df_clean = resampled.dropna(subset=['open', 'high', 'low', 'close']).copy()

    df_clean = df_clean.copy()
    df_clean['date'] = df_clean.index.astype(str)
    return df_clean


# =========================================================================
# STATE MACHINE & TRADE SIMULATION
# =========================================================================
def simulate_trades(df: pd.DataFrame):
    """
    Simulates trades following:
    1. 1h close > Weekly R3 (with Daily > 200 EMA yesterday & today)
    2. Wait for Supertrend (7, 3) to print Sell signal
    3. Within next 2 weeks, wait for Supertrend (7, 3) to print Buy signal
    4. Buy at the High of this Supertrend Buy candle
    5. TP: +10% | SL: Supertrend Sell signal
    """
    n = len(df)
    open_ = df['open'].to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    times = df.index.to_pydatetime()
    date_strs = df['date'].astype(str).to_numpy()

    st_line, st_dir = compute_supertrend(df, SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER)
    weekly_r3 = compute_weekly_pivot_r3(df)
    daily_ema_ok, daily_ema_val = compute_daily_200_ema_filter(df, DAILY_EMA_PERIOD)

    long_entry = np.zeros(n, dtype=bool)
    signal = np.zeros(n, dtype=bool)
    tp_arr = np.full(n, np.nan)
    sl_arr = np.full(n, np.nan)
    trades = []

    # States:
    # "IDLE"
    # "AWAITING_ST_SELL"
    # "AWAITING_ST_BUY"
    # "AWAITING_BREAKOUT"
    # "IN_TRADE"
    state = "IDLE"

    trigger_time = None
    st_sell_time = None
    qualifying_high = None
    breakout_bars_waited = 0

    trade_entry_idx = None
    entry_price = None
    tp_price = None
    mae = 0.0
    mfe = 0.0

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
        # 1. Manage Active Trade
        if state == "IN_TRADE":
            mae = max(mae, (entry_price - low[i]) / entry_price * 100.0)
            mfe = max(mfe, (high[i] - entry_price) / entry_price * 100.0)

            # Check Target Profit (+10%)
            if high[i] >= tp_price:
                exit_px = tp_price if open_[i] <= tp_price else open_[i]
                close_trade(i, exit_px, f"Target Profit (+{TP_PCT}%)")
                state = "IDLE"
                continue

            # Check Stop Loss (Supertrend Sell Signal)
            # Supertrend flips from 1 to -1
            if st_dir[i] == -1 and st_dir[i - 1] == 1:
                close_trade(i, close[i], "Stop Loss (Supertrend Sell Signal)")
                state = "IDLE"
                continue

            # Intraday square-off toggle if enabled
            if INTRA_DAY_ONLY and (times[i].hour >= 15 and times[i].minute >= 15):
                close_trade(i, close[i], "EOD Square-off")
                state = "IDLE"
                continue

            continue

        # 2. State: AWAITING_BREAKOUT (Buy-stop armed at qualifying_high)
        if state == "AWAITING_BREAKOUT":
            breakout_bars_waited += 1

            # Invalidation: if Supertrend flips to Sell before breakout, cancel
            if st_dir[i] == -1 and st_dir[i - 1] == 1:
                state = "IDLE"
                continue

            # Breakout check: High breaks qualifying_high
            if high[i] > qualifying_high:
                trade_entry_idx = i
                entry_price = qualifying_high if open_[i] <= qualifying_high else open_[i]
                tp_price = entry_price * (1.0 + TP_PCT / 100.0)

                long_entry[i] = True
                tp_arr[i] = TP_PCT
                state = "IN_TRADE"

                mae = (entry_price - low[i]) / entry_price * 100.0
                mfe = (high[i] - entry_price) / entry_price * 100.0

                # Same bar TP check
                if high[i] >= tp_price:
                    exit_px = tp_price if open_[i] <= tp_price else open_[i]
                    close_trade(i, exit_px, f"Target Profit (+{TP_PCT}% Same Bar)")
                    state = "IDLE"
                continue

            if breakout_bars_waited >= MAX_BREAKOUT_WAIT_BARS:
                state = "IDLE"
                continue

        # 3. State: AWAITING_ST_BUY (Within 2 weeks from the initial Weekly R3 trigger candle)
        if state == "AWAITING_ST_BUY":
            # Check 2-week expiration from initial Weekly R3 trigger candle
            elapsed = times[i] - trigger_time
            if elapsed > timedelta(days=MAX_TRIGGER_WINDOW_DAYS):
                # 2 weeks expired from trigger candle without Supertrend buy flip -> reset
                state = "IDLE"
                continue

            # Supertrend flips from Bearish (-1) to Bullish (1) -> BUY SIGNAL!
            if st_dir[i] == 1 and st_dir[i - 1] == -1:
                signal[i] = True
                qualifying_high = high[i]
                breakout_bars_waited = 0
                state = "AWAITING_BREAKOUT"
                continue

        # 4. State: AWAITING_ST_SELL (Within 2 weeks from the initial Weekly R3 trigger candle)
        if state == "AWAITING_ST_SELL":
            elapsed = times[i] - trigger_time
            if elapsed > timedelta(days=MAX_TRIGGER_WINDOW_DAYS):
                # 2 weeks expired from trigger candle without Supertrend sell flip -> reset
                state = "IDLE"
                continue

            # Supertrend flips from Bullish (1) to Bearish (-1) -> Sell Signal
            if st_dir[i] == -1 and st_dir[i - 1] == 1:
                state = "AWAITING_ST_BUY"
                continue

        # 5. State: IDLE -> Watch for 1h close > Weekly R3 & Daily > 200 EMA
        if state == "IDLE":
            r3_val = weekly_r3[i]
            r3_pass = (not np.isnan(r3_val)) and (close[i] > r3_val)
            ema_pass = daily_ema_ok[i]

            if r3_pass and ema_pass:
                trigger_time = times[i]
                # If Supertrend is currently bullish, wait for sell
                if st_dir[i] == 1:
                    state = "AWAITING_ST_SELL"
                else:
                    # If Supertrend is already in Sell at trigger, wait for buy within 2 weeks of trigger_time
                    state = "AWAITING_ST_BUY"

    if state == "IN_TRADE":
        close_trade(n - 1, close[-1], "End of Data", is_open=True)

    indicators = {
        'Weekly_R3': weekly_r3,
        'Daily_EMA200': daily_ema_val,
        'Supertrend_Line': st_line,
        'Supertrend_Dir': st_dir,
        'Daily_200EMA_Pass': daily_ema_ok,
    }

    return trades, long_entry, signal, tp_arr, sl_arr, indicators


# =========================================================================
# SCREENER & BACKTESTER INTERFACE
# =========================================================================
def backtest(df: pd.DataFrame) -> dict:
    """Standard interface for Stock Screener backtest sandbox."""
    df_1h = _prepare_1hour_df(df)
    n = len(df_1h)

    empty_res = {
        "trades": [],
        "long_entry": pd.Series(False, index=df_1h.index),
        "entries": pd.Series(False, index=df_1h.index),
        "signal": pd.Series(False, index=df_1h.index),
        "tp_pct": pd.Series(TP_PCT, index=df_1h.index),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=df_1h.index),
        "df": df_1h
    }

    if n < 10:
        return empty_res

    trades, long_entry_arr, signal_arr, tp_pct_arr, sl_pct_arr, indicators = simulate_trades(df_1h)

    out_df = df_1h.copy()
    for k, v in indicators.items():
        out_df[k] = v
    out_df['Long_Entry'] = long_entry_arr
    out_df['Signal'] = signal_arr

    return {
        "trades": trades,
        "long_entry": pd.Series(long_entry_arr, index=df_1h.index),
        "entries": pd.Series(long_entry_arr, index=df_1h.index),
        "signal": pd.Series(signal_arr, index=df_1h.index),
        "tp_pct": pd.Series(tp_pct_arr, index=df_1h.index).fillna(TP_PCT),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=df_1h.index),
        "df": out_df
    }

# Screener compatibility alias
screen = backtest

"""
15-Minute Intraday Strategy: Dual RSI (80/85) + 2M Volume Peak + Daily R2 (Short | TP VWAP | SL 2%)
===================================================================================================
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).
Timeframe: 15-Minute candles (automatically resamples 1-min or 5-min data if provided).

STRATEGY CRITERIA:
1. Timeframe (TF): 15 Min
2. Sell / Short Signal (Overbought Exhaustion Reversal):
   Two consecutive high-volume candles (Candle 1 [t-1] and Candle 2 [t]):
   - Volume of both candles must be >= 200,000 (2,00,000)
   - Candle 1 [t-1]: 14-period Wilder RSI > 80.0
   - Candle 2 [t]:   14-period Wilder RSI > 85.0
   - Extreme Volume: Either Candle 1 OR Candle 2 must have the highest volume
     in the past 2 months (~42 trading days / 1,050 fifteen-minute bars).
   - Daily Pivot R2: Both Candle 1 and Candle 2 must close above Daily R2
     (computed from the prior completed trading day's Daily High, Low, Close).
3. Entry Execution:
   - Enter SHORT (Sell) at the Close of Candle 2 (exactly where we entered before).
   - Restrictions:
     * No new entries post 1:00 PM IST (13:00 cutoff).
     * Maximum 1 trade per day.
4. Target Profit (TP):
   - Dynamic Target: Session VWAP!
   - When price falls to or below the session VWAP (Low <= VWAP), cover short at VWAP.
5. Stop Loss (SL):
   - Fixed 2.0% above the entry price:
     sl_price = entry_price * (1.0 + 2.0 / 100.0) = entry_price * 1.02.
   - When price rises to or above sl_price (High >= sl_price), exit at sl_price.
6. Intraday Square-off:
   - Open short positions square off at 15:15 IST (EOD close).
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import time as dtime

# =========================================================================
# CONFIGURABLE PARAMETERS
# =========================================================================
TF_MINUTES = 15                  # Base strategy timeframe in minutes
VOLUME_FLOOR = 200_000           # Minimum volume required for both candles (2,00,000)
RSI_PERIOD = 14                  # Wilder's smoothed RSI period
RSI_CANDLE1_MIN = 80.0           # Candle 1 RSI threshold (> 80.0)
RSI_CANDLE2_MIN = 85.0           # Candle 2 RSI threshold (> 85.0)

# Volume Lookback: 2 months (~42 trading days * 25 fifteen-minute bars = 1,050 bars)
VOLUME_LOOKBACK_BARS = 1050

SL_PCT = 2.0                     # Fixed 2.0% Stop Loss from entry price
DEFAULT_TP_PCT = 3.0             # Fallback display TP % for template UI
ENTRY_CUTOFF_TIME = dtime(13, 0) # No new entries post 1:00 PM IST (13:00 cutoff)
SQUARE_OFF_TIME = dtime(15, 15)  # EOD Intraday square-off time (15:15 IST)
REQUIRE_SAME_DAY_SETUP = True    # Candle 1 and Candle 2 must belong to the same session


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


def compute_daily_pivot_r2(df: pd.DataFrame) -> np.ndarray:
    """
    Computes Classical Daily Pivot R2 from the PRIOR completed calendar day's OHLC:
        Pivot = (High_prev + Low_prev + Close_prev) / 3.0
        R2    = Pivot + (High_prev - Low_prev)
    Shifted by 1 day so today's intraday bars reference yesterday's completed levels.
    """
    day_period = df.index.to_period('D')
    d_ohlc = df.groupby(day_period).agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    )
    pivot = (d_ohlc['high'] + d_ohlc['low'] + d_ohlc['close']) / 3.0
    r2 = pivot + (d_ohlc['high'] - d_ohlc['low'])

    r2_lagged = r2.shift(1)
    return r2_lagged.reindex(day_period).to_numpy(dtype=float)


def compute_prior_max_volume(volume: np.ndarray, lookback_bars: int = 1050) -> np.ndarray:
    """
    Computes rolling maximum volume over the prior lookback window (excluding current bar).
    """
    vol_series = pd.Series(volume)
    vol_max = vol_series.shift(1).rolling(
        lookback_bars, min_periods=1
    ).max().to_numpy(dtype=float)
    return vol_max


# =========================================================================
# DATA PREPARATION & RESAMPLING
# =========================================================================
def _prepare_15min_df(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans and standardizes the input dataframe to 15-minute bars."""
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

    df_clean = df_clean.dropna(subset=['open', 'high', 'low', 'close', 'volume'])

    if len(df_clean) > 5:
        median_spacing = pd.Series(df_clean.index).diff().median()
        if median_spacing < pd.Timedelta(minutes=14):
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

            resampled = df_clean.resample('15min', closed='left', label='left').agg(agg_dict)
            df_clean = resampled.dropna(subset=['open', 'high', 'low', 'close']).copy()

    df_clean = df_clean.copy()
    df_clean['date'] = df_clean.index.astype(str)
    return df_clean


# =========================================================================
# SIGNAL EVALUATION
# =========================================================================
def evaluate_signals(df: pd.DataFrame):
    """
    Evaluates strategy indicators and the two-consecutive candle sell trigger.
    Returns:
        signal (np.ndarray of bool): True on bar [i] when the 2-candle setup completes.
        indicators (dict): RSI, Daily R2, VWAP, Max Volume.
    """
    n = len(df)
    close = df['close'].to_numpy(dtype=float)
    volume = df['volume'].to_numpy(dtype=float)
    day = df.index.normalize()
    tod = df.index.time

    rsi = compute_rsi(pd.Series(close, index=df.index), RSI_PERIOD)
    vwap = compute_session_vwap(df)
    daily_r2 = compute_daily_pivot_r2(df)
    vol_max_prior = compute_prior_max_volume(volume, VOLUME_LOOKBACK_BARS)

    c_vol_floor = volume >= VOLUME_FLOOR
    c_above_r2 = (~np.isnan(daily_r2)) & (close > daily_r2)
    c_vol_peak = np.where(~np.isnan(vol_max_prior), volume >= vol_max_prior, False)

    signal = np.zeros(n, dtype=bool)

    for i in range(1, n):
        if REQUIRE_SAME_DAY_SETUP and (day[i] != day[i - 1]):
            continue

        if tod[i] > ENTRY_CUTOFF_TIME:
            continue

        # Check Candle 1 (i-1): Vol >= 200k, RSI > 80, Close > Daily R2
        candle1_valid = c_vol_floor[i - 1] and (rsi[i - 1] > RSI_CANDLE1_MIN) and c_above_r2[i - 1]

        # Check Candle 2 (i): Vol >= 200k, RSI > 85, Close > Daily R2
        candle2_valid = c_vol_floor[i] and (rsi[i] > RSI_CANDLE2_MIN) and c_above_r2[i]

        either_vol_peak = c_vol_peak[i - 1] or c_vol_peak[i]

        if candle1_valid and candle2_valid and either_vol_peak:
            signal[i] = True

    # Filter signal: Only the first trigger per day before 1:00 PM is retained
    day_series = df.index.normalize()
    first_hit_mask = np.zeros(n, dtype=bool)
    seen_signal_days = set()
    for i in range(n):
        if signal[i]:
            d = day_series[i]
            if d not in seen_signal_days and tod[i] <= ENTRY_CUTOFF_TIME:
                seen_signal_days.add(d)
                first_hit_mask[i] = True
    signal = first_hit_mask

    indicators = {
        'RSI_15m': rsi,
        'VWAP': vwap,
        'Daily_R2': daily_r2,
        'Vol_Max_Prior_2M': vol_max_prior,
        'Cond_Vol_Floor': c_vol_floor,
        'Cond_Above_Daily_R2': c_above_r2,
        'Cond_Vol_Peak_2M': c_vol_peak,
    }

    return signal, indicators


# =========================================================================
# TRADE SIMULATION (SHORT / SELL STATE MACHINE)
# =========================================================================
def simulate_trades(df: pd.DataFrame):
    """
    Simulates SHORT (Sell) trades:
    - Entry: Short at close of qualifying candle.
    - TP: Target is Session VWAP (exit when Low <= VWAP).
    - SL: Fixed 2.0% above entry price (exit when High >= entry * 1.02).
    - Intraday EOD square-off at 15:15 IST.
    """
    n = len(df)
    open_ = df['open'].to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    date_strs = df['date'].astype(str).to_numpy()
    day = df.index.normalize()
    tod = df.index.time

    signal, indicators = evaluate_signals(df)
    vwap = indicators['VWAP']

    short_entry = np.zeros(n, dtype=bool)
    tp_arr = np.full(n, np.nan)
    sl_arr = np.full(n, np.nan)
    trades = []

    state = "IDLE"  # "IDLE", "IN_TRADE"
    trade_entry_idx = None
    entry_price = None
    sl_price = None
    mae = 0.0
    mfe = 0.0
    trade_day = None
    traded_days = set()

    def close_trade(exit_idx, exit_px, reason, is_open=False):
        trades.append({
            "entry_date": date_strs[trade_entry_idx],
            "entry_price": round(float(entry_price), 2),
            "exit_date": date_strs[exit_idx],
            "exit_price": round(float(exit_px), 2),
            "exit_reason": reason,
            "trade_type": "SHORT",
            "side": "SHORT",
            "direction": "SHORT",
            "mae_pct": round(float(mae), 2),
            "mfe_pct": round(float(mfe), 2),
            "is_open": bool(is_open),
        })

    for i in range(n):
        # Session boundary check
        if state == "IN_TRADE" and day[i] != trade_day:
            close_trade(i - 1, close[i - 1], "EOD Square-off (Session End)")
            state = "IDLE"

        # Manage Open Short Trade
        if state == "IN_TRADE":
            # In a short trade:
            # Favorable excursion (profit) is downward: entry_price - low[i]
            # Adverse excursion (loss) is upward: high[i] - entry_price
            mfe = max(mfe, (entry_price - low[i]) / entry_price * 100.0)
            mae = max(mae, (high[i] - entry_price) / entry_price * 100.0)

            curr_vwap = vwap[i]

            # 1. Target Profit Check: Price reaches session VWAP
            if not np.isnan(curr_vwap) and low[i] <= curr_vwap:
                exit_px = curr_vwap if open_[i] >= curr_vwap else open_[i]
                close_trade(i, exit_px, "Target Profit (Session VWAP Reached)")
                state = "IDLE"

            # 2. Stop Loss (2.0%) Check: Price rises to or above sl_price
            elif high[i] >= sl_price:
                exit_px = sl_price if open_[i] <= sl_price else open_[i]
                close_trade(i, exit_px, f"Stop Loss ({SL_PCT}% Hit)")
                state = "IDLE"

            # 3. Intraday EOD Square-off (15:15 IST)
            elif tod[i] >= SQUARE_OFF_TIME or (i + 1 < n and day[i + 1] != day[i]):
                close_trade(i, close[i], "EOD Square-off (15:15)")
                state = "IDLE"

            if state == "IN_TRADE":
                sl_arr[i] = sl_price
                if not np.isnan(curr_vwap):
                    tp_arr[i] = curr_vwap

        # Check for new Short Sell Signal (strictly max 1 trade per day, entry <= 1:00 PM)
        if state == "IDLE" and signal[i]:
            if day[i] in traded_days or tod[i] > ENTRY_CUTOFF_TIME:
                continue

            traded_days.add(day[i])
            trade_entry_idx = i
            entry_price = close[i]
            sl_price = entry_price * (1.0 + SL_PCT / 100.0)
            curr_vwap = vwap[i]
            trade_day = day[i]

            short_entry[i] = True
            state = "IN_TRADE"

            mfe = (entry_price - low[i]) / entry_price * 100.0
            mae = (high[i] - entry_price) / entry_price * 100.0

            # Intrabar checks on entry candle itself
            if not np.isnan(curr_vwap) and low[i] <= curr_vwap:
                exit_px = curr_vwap
                close_trade(i, exit_px, "Target Profit (Session VWAP Reached Same Bar)")
                state = "IDLE"
            elif high[i] >= sl_price:
                exit_px = sl_price
                close_trade(i, exit_px, f"Stop Loss ({SL_PCT}% Hit Same Bar)")
                state = "IDLE"

    # Close any open trade at end of data
    if state == "IN_TRADE":
        close_trade(n - 1, close[-1], "End of Data", is_open=True)

    return trades, short_entry, signal, tp_arr, sl_arr, indicators


# =========================================================================
# SCREENER & BACKTESTER INTERFACE
# =========================================================================
def backtest(df: pd.DataFrame) -> dict:
    """
    Standard interface for Stock Screener backtest and sandbox execution.
    """
    df_15m = _prepare_15min_df(df)
    n = len(df_15m)

    empty_res = {
        "trades": [],
        "long_entry": pd.Series(False, index=df_15m.index),
        "short_entry": pd.Series(False, index=df_15m.index),
        "entries": pd.Series(False, index=df_15m.index),
        "signal": pd.Series(False, index=df_15m.index),
        "tp_pct": pd.Series(DEFAULT_TP_PCT, index=df_15m.index),
        "sl_pct": pd.Series(SL_PCT, index=df_15m.index),
        "df": df_15m
    }

    if n < 10:
        return empty_res

    trades, entry_arr, signal_arr, tp_arr, sl_arr, indicators = simulate_trades(df_15m)

    out_df = df_15m.copy()
    for k, v in indicators.items():
        out_df[k] = v
    out_df['Short_Entry'] = entry_arr
    out_df['Signal'] = signal_arr
    out_df['Stop_Loss_Price'] = sl_arr
    out_df['Target_VWAP'] = tp_arr

    return {
        "trades": trades,
        "long_entry": pd.Series(entry_arr, index=df_15m.index),   # Provided for UI widget compatibility
        "short_entry": pd.Series(entry_arr, index=df_15m.index),
        "entries": pd.Series(entry_arr, index=df_15m.index),
        "signal": pd.Series(signal_arr, index=df_15m.index),
        "tp_pct": pd.Series(DEFAULT_TP_PCT, index=df_15m.index),
        "sl_pct": pd.Series(SL_PCT, index=df_15m.index),
        "df": out_df
    }

# Screener compatibility alias
screen = backtest

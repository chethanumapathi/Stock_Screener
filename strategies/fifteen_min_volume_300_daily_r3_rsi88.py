"""
15-Min Volume Breakout (300) + Daily R3 + Monthly R1 + RSI>88 Long (Buy High | TP 3% | VWAP & 15m High SL)
=============================================================================================================
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).
Base Timeframe: 5-Minute candles (or 15-Minute candles).

RULES IMPLEMENTED:
1. 15-MIN VOLUME BREAKOUT:
   Current 15-min Volume > highest 15-min Volume of the prior 300 fifteen-minute bars
   (current bar excluded from baseline).

2. 15-MIN CLOSE > DAILY R3:
   15-min Close > Daily Pivot R3
   Classical Daily Pivot: Pivot = (High_prev + Low_prev + Close_prev) / 3.0
   Classical Daily R3:    R3    = High_prev + 2.0 * (Pivot - Low_prev)
   (Computed from the prior completed calendar day's OHLC, held constant across the current day).

3. 15-MIN CLOSE > MONTHLY R1:
   15-min Close > Monthly Pivot R1
   Classical Monthly Pivot: Monthly PP = (High_m_prev + Low_m_prev + Close_m_prev) / 3.0
   Classical Monthly R1:    Monthly R1 = 2.0 * Monthly PP - Low_m_prev
   (Computed from the prior completed calendar month's OHLC, held constant across the current month).

4. 15-MIN RSI > 88:
   Wilder's 14-period smoothed RSI on 15-minute Close > 88.0.

5. TIME CUTOFF:
   Setup must qualify before or at 12:00 PM IST (12:00 cutoff). No new setups/trades post 12:00 PM.

6. ENTRY EXECUTION:
   We buy at the HIGH of this qualifying setup candle (placed as buy-stop).
   When a subsequent candle trades at/above this high (before 12:00 PM cutoff),
   enter LONG at max(Open, Setup_High).

7. TARGET PROFIT (TP):
   Fixed +3.0% from entry price (TP = Entry * 1.03).
   Once TP is achieved that day, no further trades that day (done for the day).

8. DYNAMIC STOP LOSS (SL):
   - Candle close below session VWAP moves SL to that candle's low (active next candle).
   - Candle close at/below the 15-min high (including breaking the 15m high intrabar
     but failing to close above it) moves SL to that candle's low (active next candle).
   - If active SL is hit (Low <= SL), exit long at SL (or Open if gapped below).

9. INTRADAY SQUARE-OFF:
   Any open position squares off at 15:15 IST (EOD close).
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import time as dtime

# =========================================================================
# CONFIGURABLE PARAMETERS
# =========================================================================
TF_MINUTES = 5                   # Base evaluation timeframe (5m or 15m)
VOLUME_LOOKBACK_15MIN = 300      # Prior 300 fifteen-minute bars volume baseline
RSI_PERIOD = 14                  # Wilder's 14-period RSI
RSI_THRESHOLD = 88.0             # 15-min RSI threshold (> 88.0)
TP_PCT = 3.0                     # Fixed +3.0% Target Profit
DEFAULT_SL_PCT = 2.0             # Fallback display SL % for template UI
ENTRY_CUTOFF_TIME = dtime(12, 0) # No new trades / setups after 12:00 PM IST
SQUARE_OFF_TIME = dtime(15, 15)  # EOD Intraday square-off at 15:15 IST


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
    """Intraday Session VWAP resetting at each trading day's open (09:15)."""
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    vol = df['volume'].astype(float)
    day = df.index.normalize()
    cum_pv = (tp * vol).groupby(day).cumsum()
    cum_vol = vol.groupby(day).cumsum().replace(0, np.nan)
    vwap = cum_pv / cum_vol
    return vwap.to_numpy(dtype=float)


def compute_daily_r3(df: pd.DataFrame) -> np.ndarray:
    """
    Computes Classical Daily Pivot R3 from the PRIOR completed calendar day's OHLC:
        Pivot = (High_prev + Low_prev + Close_prev) / 3.0
        R3    = High_prev + 2.0 * (Pivot - Low_prev)
    Shifted by 1 day so today's intraday bars reference yesterday's completed levels.
    """
    day_period = df.index.to_period('D')
    d_ohlc = df.groupby(day_period).agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    )
    pivot = (d_ohlc['high'] + d_ohlc['low'] + d_ohlc['close']) / 3.0
    r3 = d_ohlc['high'] + 2.0 * (pivot - d_ohlc['low'])
    r3_lagged = r3.shift(1)
    return r3_lagged.reindex(day_period).to_numpy(dtype=float)


def compute_monthly_r1(df: pd.DataFrame, symbol: str = None) -> np.ndarray:
    """
    Computes Classical Monthly Pivot R1 from the PRIOR completed calendar month's OHLC:
        Pivot = (High_m_prev + Low_m_prev + Close_m_prev) / 3.0
        R1    = 2.0 * Pivot - Low_m_prev
    Shifted by 1 month so each month's bars reference the previous completed month.
    If the intraday dataframe starts mid-month or has fewer than 2 months,
    seamlessly supplements prior month OHLC from daily parquet cache (data/adjusted_daily/{symbol}.parquet).
    """
    month_period = df.index.to_period('M')
    m_ohlc = df.groupby(month_period).agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    )
    if symbol:
        daily_path = os.path.join('data', 'adjusted_daily', f'{symbol}.parquet')
        if os.path.exists(daily_path):
            try:
                df_daily = pd.read_parquet(daily_path)
                d_idx = pd.DatetimeIndex(pd.to_datetime(df_daily['date'] if 'date' in df_daily.columns else df_daily.index))
                df_daily.index = d_idx
                d_m_period = d_idx.to_period('M')
                d_m_ohlc = df_daily.groupby(d_m_period).agg(
                    high=('high', 'max'),
                    low=('low', 'min'),
                    close=('close', 'last')
                )
                m_ohlc = d_m_ohlc.combine_first(m_ohlc).sort_index()
            except Exception:
                pass

    m_pivot = (m_ohlc['high'] + m_ohlc['low'] + m_ohlc['close']) / 3.0
    m_r1 = 2.0 * m_pivot - m_ohlc['low']
    m_r1_lagged = m_r1.shift(1)
    return month_period.map(m_r1_lagged).to_numpy(dtype=float)


# =========================================================================
# DATA PREPARATION & CLEANING
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

    df_clean = df_clean.dropna(subset=['open', 'high', 'low', 'close', 'volume'])
    df_clean['date'] = df_clean.index.astype(str)
    return df_clean


def _get_market_cap(df: pd.DataFrame, symbol: str = None) -> float:
    for c in df.columns:
        if str(c).lower() == 'market_cap_cr':
            s_vals = pd.to_numeric(df[c], errors='coerce').dropna()
            if not s_vals.empty:
                return float(s_vals.iloc[-1])
    try:
        import app
        if symbol:
            m = app.get_market_cap_cr(symbol, fetch_online=False)
            if m and m > 0:
                return float(m)
    except Exception:
        pass
    return 0.0


# =========================================================================
# STRATEGY & TRADE SIMULATION
# =========================================================================
def simulate_strategy(df_input: pd.DataFrame):
    df_clean = _clean_df(df_input)
    n_bars = len(df_clean)
    if n_bars < 30:
        return [], np.zeros(n_bars, dtype=bool), np.zeros(n_bars, dtype=bool), np.full(n_bars, np.nan), np.full(n_bars, np.nan), {}

    # Extract symbol
    symbol = None
    for c in ('symbol', 'Symbol', 'ticker', 'Ticker'):
        if c in df_clean.columns:
            symbol = str(df_clean[c].iloc[-1]).upper().replace('.NS', '').strip()
            break
    market_cap_cr = _get_market_cap(df_clean, symbol)

    # 1. Resample to 15-minute candles for higher-timeframe metrics
    p15 = df_clean.index.floor('15min')
    o15 = df_clean.groupby(p15).agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        volume=('volume', 'sum')
    )

    # 2. Compute 15-minute indicators
    vol15 = o15['volume'].to_numpy(dtype=float)
    # 300 15-min bars volume baseline (excluding current bar)
    vol15_prior_max = pd.Series(vol15, index=o15.index).shift(1).rolling(
        VOLUME_LOOKBACK_15MIN, min_periods=min(50, len(o15))
    ).max().to_numpy(dtype=float)

    rsi15 = compute_rsi(o15['close'], RSI_PERIOD)
    r3_15m = compute_daily_r3(o15)
    mr1_15m = compute_monthly_r1(o15, symbol=symbol)

    c_vol_brk_15m = (vol15 > vol15_prior_max) & (~np.isnan(vol15_prior_max))
    c_r3_15m = (o15['close'].to_numpy(dtype=float) > r3_15m) & (~np.isnan(r3_15m))
    c_mr1_15m = (o15['close'].to_numpy(dtype=float) > mr1_15m) & (~np.isnan(mr1_15m))
    c_rsi_15m = rsi15 > RSI_THRESHOLD
    tod_15m = o15.index.time
    c_time_15m = np.array([t <= ENTRY_CUTOFF_TIME for t in tod_15m])

    # 15m Qualifying setup (Volume > 300-bar max, Close > Daily R3, Close > Monthly R1, RSI > 88, Time <= 12:00)
    qual_15m = c_vol_brk_15m & c_r3_15m & c_mr1_15m & c_rsi_15m & c_time_15m
    qual_15m_buckets = set(o15.index[qual_15m])

    # Map 15m indicators back onto base dataframe
    o15_reindexed = o15.reindex(p15)
    vol15_on_5m = o15_reindexed['volume'].to_numpy(dtype=float)
    vol15_prior_max_on_5m = pd.Series(vol15_prior_max, index=o15.index).reindex(p15).to_numpy(dtype=float)
    rsi15_on_5m = pd.Series(rsi15, index=o15.index).reindex(p15).to_numpy(dtype=float)
    r3_on_5m = pd.Series(r3_15m, index=o15.index).reindex(p15).to_numpy(dtype=float)
    mr1_on_5m = pd.Series(mr1_15m, index=o15.index).reindex(p15).to_numpy(dtype=float)
    vwap_5m = compute_session_vwap(df_clean)

    # 3. State Machine Trade Simulation on 5m execution bars
    idx_5m = df_clean.index
    open_5m = df_clean['open'].to_numpy(dtype=float)
    high_5m = df_clean['high'].to_numpy(dtype=float)
    low_5m = df_clean['low'].to_numpy(dtype=float)
    close_5m = df_clean['close'].to_numpy(dtype=float)
    date_strs = df_clean['date'].astype(str).to_numpy()
    tod_5m = df_clean.index.time
    day_5m = df_clean.index.normalize()

    bucket_5m = df_clean.index.floor('15min')
    bucket_high_map = o15['high'].to_dict()

    long_entry_arr = np.zeros(n_bars, dtype=bool)
    scan_pass_arr = np.zeros(n_bars, dtype=bool)
    tp_arr = np.full(n_bars, np.nan)
    sl_arr = np.full(n_bars, np.nan)
    setup_high_arr = np.full(n_bars, np.nan)
    trades = []

    state = "IDLE"  # "IDLE", "AWAITING_BREAKOUT", "IN_TRADE"
    setup_day = None
    setup_15m_high = None
    entry_price = None
    tp_price = None
    active_sl = None
    pending_sl_next_bar = None
    sl_reason = ""
    trade_entry_idx = None
    mae = 0.0
    mfe = 0.0
    tp_hit_today = False

    def close_trade(exit_idx, exit_px, reason, is_open=False):
        trades.append({
            "entry_date": date_strs[trade_entry_idx],
            "entry_price": round(float(entry_price), 2),
            "exit_date": date_strs[exit_idx],
            "exit_price": round(float(exit_px), 2),
            "exit_reason": reason,
            "trade_type": "LONG",
            "side": "LONG",
            "direction": "LONG",
            "pnl_pct": round(float((exit_px - entry_price) / entry_price * 100.0), 2),
            "mae_pct": round(float(mae), 2),
            "mfe_pct": round(float(mfe), 2),
            "is_open": bool(is_open)
        })

    for i in range(n_bars):
        curr_t = idx_5m[i]
        curr_tod = tod_5m[i]
        curr_day = day_5m[i]

        # Daily Session Boundary Reset
        if i > 0 and curr_day != day_5m[i - 1]:
            if state == "IN_TRADE":
                close_trade(i - 1, close_5m[i - 1], "EOD Square-off (Session Rollover)")
            state = "IDLE"
            setup_day = None
            setup_15m_high = None
            tp_hit_today = False
            active_sl = None
            pending_sl_next_bar = None

        # Activate SL shifted from prior candle's close
        if pending_sl_next_bar is not None:
            active_sl = pending_sl_next_bar
            pending_sl_next_bar = None

        time_ok = curr_tod <= ENTRY_CUTOFF_TIME
        is_eod = curr_tod >= SQUARE_OFF_TIME

        # -----------------------------------------------------------------
        # 1. MANAGE ACTIVE TRADE (IN_TRADE)
        # -----------------------------------------------------------------
        if state == "IN_TRADE":
            mfe = max(mfe, (high_5m[i] - entry_price) / entry_price * 100.0)
            mae = min(mae, (low_5m[i] - entry_price) / entry_price * 100.0)

            tp_arr[i] = tp_price
            if active_sl is not None:
                sl_arr[i] = active_sl

            # A) Check Stop Loss (active from previous candle's low)
            if active_sl is not None and low_5m[i] <= active_sl:
                exit_p = active_sl if open_5m[i] >= active_sl else open_5m[i]
                close_trade(i, exit_p, f"SL ({sl_reason})")
                state = "IDLE"
                active_sl = None
                continue

            # B) Check Target Profit (+3.0%)
            elif high_5m[i] >= tp_price:
                exit_p = tp_price if open_5m[i] <= tp_price else open_5m[i]
                close_trade(i, exit_p, "Target Profit (+3.0%)")
                state = "IDLE"
                tp_hit_today = True  # Target profit hit: done for the day
                active_sl = None
                continue

            # C) Check EOD Square-off (15:15 IST)
            elif is_eod:
                close_trade(i, close_5m[i], "EOD Square-off (15:15)")
                state = "IDLE"
                active_sl = None
                continue

            # D) Update SL on this candle close (becomes active on NEXT candle):
            #    Rule 1: Close below session VWAP moves SL to that candle's low
            #    Rule 2: Close at/below 15-min high moves SL to that candle's low
            close_below_vwap = (not np.isnan(vwap_5m[i])) and (close_5m[i] < vwap_5m[i])
            close_below_15m_high = (setup_15m_high is not None) and (close_5m[i] <= setup_15m_high)

            if close_below_vwap or close_below_15m_high:
                pending_sl_next_bar = low_5m[i]
                if close_below_vwap and close_below_15m_high:
                    sl_reason = "Close < VWAP & <= 15m High"
                elif close_below_vwap:
                    sl_reason = "Close < VWAP"
                else:
                    sl_reason = "Close <= 15m High"

            continue

        # -----------------------------------------------------------------
        # 2. AWAITING BREAKOUT (Buy at the high of the qualifying setup candle)
        # -----------------------------------------------------------------
        if state == "AWAITING_BREAKOUT":
            if not time_ok or is_eod or curr_day != setup_day:
                state = "IDLE"
                continue

            setup_high_arr[i] = setup_15m_high

            # Buy-stop fill: High trades at or above setup_15m_high
            if high_5m[i] >= setup_15m_high:
                entry_price = max(open_5m[i], setup_15m_high)
                tp_price = round(entry_price * (1.0 + TP_PCT / 100.0), 2)
                trade_entry_idx = i
                long_entry_arr[i] = True
                tp_arr[i] = tp_price

                state = "IN_TRADE"
                active_sl = None
                pending_sl_next_bar = None
                mae = 0.0
                mfe = 0.0

                # Same bar Target Profit check
                if high_5m[i] >= tp_price:
                    exit_p = tp_price
                    close_trade(i, exit_p, "Target Profit (+3.0% Same Bar)")
                    state = "IDLE"
                    tp_hit_today = True

                continue

        # -----------------------------------------------------------------
        # 3. DETECT NEW QUALIFYING 15-MIN SETUP COMPLETION
        # -----------------------------------------------------------------
        curr_bucket = bucket_5m[i]
        is_bucket_end = (i + 1 == n_bars) or (bucket_5m[i + 1] != curr_bucket)

        if is_bucket_end and curr_bucket in qual_15m_buckets:
            scan_pass_arr[i] = True
            if time_ok and not is_eod and not tp_hit_today and state == "IDLE":
                setup_15m_high = bucket_high_map.get(curr_bucket, high_5m[i])
                setup_day = curr_day
                state = "AWAITING_BREAKOUT"
                setup_high_arr[i] = setup_15m_high

    # Close any open trade at end of data
    if state == "IN_TRADE":
        close_trade(n_bars - 1, close_5m[-1], "Open", is_open=True)

    indicators = {
        'Vol_15m': vol15_on_5m,
        'Vol_Max_Prior_300_15m': vol15_prior_max_on_5m,
        'RSI_15m': np.round(rsi15_on_5m, 2),
        'Daily_R3': np.round(r3_on_5m, 2),
        'Monthly_R1': np.round(mr1_on_5m, 2),
        'VWAP': np.round(vwap_5m, 2),
        'Setup_15m_High': setup_high_arr,
        'Market_Cap_Cr': market_cap_cr
    }

    return trades, long_entry_arr, scan_pass_arr, tp_arr, sl_arr, indicators


# =========================================================================
# INTERFACES: BACKTEST & SCREENER SANDBOX
# =========================================================================
def backtest(df: pd.DataFrame) -> dict:
    """
    Standard interface for Stock Screener backtest sandbox and diagnostics.
    """
    df_clean = _clean_df(df)
    n = len(df_clean)

    empty_res = {
        "trades": [],
        "long_entry": pd.Series(False, index=df_clean.index),
        "entries": pd.Series(False, index=df_clean.index),
        "signal": pd.Series(False, index=df_clean.index),
        "tp_pct": pd.Series(TP_PCT, index=df_clean.index),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=df_clean.index),
        "df": df_clean
    }

    if n < 10:
        return empty_res

    trades, entry_arr, scan_arr, tp_arr, sl_arr, indicators = simulate_strategy(df_clean)

    out_df = df_clean.copy()
    for k, v in indicators.items():
        out_df[k] = v
    out_df['Scan_Pass'] = scan_arr
    out_df['Long_Entry'] = entry_arr
    out_df['Stop_Loss_Price'] = sl_arr
    out_df['Target_Profit_Price'] = tp_arr

    # Primary signal for screener and backtester
    primary_signal = scan_arr if scan_arr.any() else entry_arr

    return {
        "trades": trades,
        "long_entry": pd.Series(entry_arr, index=df_clean.index),
        "entries": pd.Series(entry_arr, index=df_clean.index),
        "signal": pd.Series(primary_signal, index=df_clean.index),
        "tp_pct": pd.Series(TP_PCT, index=df_clean.index),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=df_clean.index),
        "df": out_df
    }

# Screener compatibility alias
screen = backtest

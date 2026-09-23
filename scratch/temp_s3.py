"""
Strong Buy Scan (5-min Volume Breakout + Weekly/Daily R2 + MCap + 15-min OBV)
  -> 15-min High Breakout Entry  |  TP 3%  |  VWAP-close SL
=============================================================================
INPUT: 5-MINUTE OHLCV. 15-min / Daily / Weekly values are derived internally.

STAGE 1 - SCAN (unchanged from the original scanner; all conditions ANDed)
  1. 5-min Volume > max Volume of prior 300 five-min bars
  2. Close > Weekly Pivot R2 (prior completed week)
  3. Close > Daily Pivot R2 (prior completed day)
  4. Market Cap > 5000 Cr
  5. 5-min Volume > 130,000
  6. 15-min OBV >= max 15-min OBV of prior 200 fifteen-min bars

STAGE 2 - ENTRY / EXIT
  a. Scan passes on a 5-min bar -> identify the 15-min candle that CONTAINS it
     (candles labelled by start time: 11:00 bar -> 11:00-11:15 candle,
      11:15 bar -> 11:15-11:30 candle). Wait for it to close; mark its HIGH.
  b. From the next 5-min bar until end of day, wait for a 5-min candle that
     CLOSES above the marked high AND has RSI(14) > 80  -> "breakout candle".
  c. Place a BUY-STOP at the breakout candle's high. Filled when a LATER candle
     trades above it (fill = max(open, stop) to account for gap-ups).
     If a newer qualifying breakout candle prints before the fill, the stop
     is re-armed at that newer candle's high.
  d. TP = entry x 1.03.
  e. SL: every time a 5-min candle CLOSES below session VWAP after entry,
     SL moves to that candle's LOW (per spec - can move up or down).
     SL is active from the next candle. Before any such close, there is no SL.
  f. Intraday: pending setups expire at day end; open trades squared off at
     the close of the SQUARE_OFF_TIME candle.
  - If SL and TP are both touched in one candle, SL is assumed first.
  - One setup / trade at a time; scan signals while busy are ignored.
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import time as dtime

# ============================================================
# CONFIG - SCAN
# ============================================================
VOLUME_LOOKBACK_5MIN = 300
MIN_VOLUME_5MIN = 130_000
OBV_LOOKBACK_15MIN = 200
OBV_EXCLUDE_CURRENT_BAR = True
MIN_MARKET_CAP_CR = 5000

# ============================================================
# CONFIG - TRADE
# ============================================================
RSI_LEN = 14
RSI_MIN_BREAKOUT = 80.0
TP_PCT = 3.0
SQUARE_OFF_TIME = dtime(15, 15)   # exit at close of the 15:15 candle; no new entries from this candle
DEFAULT_SL_PCT = 2.0              # display-only fallback for sl_pct (template convention); real SL = VWAP-candle low
DEBUG = True

# Toggle individual scan conditions (set False to isolate which one blocks trades)
USE_VOL_BREAKOUT = True
USE_WEEKLY_R2 = True
USE_DAILY_R2 = True
USE_VOL_FLOOR = True
USE_OBV_15M = True


def _log(msg):
    if DEBUG:
        print(msg)


# ============================================================
# INDICATORS
# ============================================================
def compute_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    obv = np.zeros(len(close))
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]
    return obv


def compute_rsi(close: pd.Series, period: int) -> np.ndarray:
    """Wilder RSI (RMA smoothing, same method as TradingView ta.rsi)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.where(avg_loss != 0, 100.0)          # no losses -> RSI 100
    return rsi.to_numpy(dtype=float)


def compute_session_vwap(price_df: pd.DataFrame) -> np.ndarray:
    """VWAP reset every trading day, typical price (H+L+C)/3."""
    tp = (price_df['high'] + price_df['low'] + price_df['close']) / 3.0
    vol = price_df['volume'].astype(float)
    day = price_df.index.normalize()
    cum_pv = (tp * vol).groupby(day).cumsum()
    cum_v = vol.groupby(day).cumsum().replace(0, np.nan)
    return (cum_pv / cum_v).to_numpy(dtype=float)


def _compute_pivot_r2(ohlc: pd.DataFrame):
    pivot = (ohlc['high'] + ohlc['low'] + ohlc['close']) / 3.0
    r2 = pivot + (ohlc['high'] - ohlc['low'])
    return pivot.shift(1), r2.shift(1)


# ============================================================
# STAGE 1 - SCAN
# ============================================================
def _scan_signal(price_df: pd.DataFrame) -> (np.ndarray, dict):
    close5 = price_df['close'].to_numpy(dtype=float)
    volume5 = price_df['volume'].to_numpy(dtype=float)

    vol_max_prior = pd.Series(volume5, index=price_df.index).shift(1).rolling(
        VOLUME_LOOKBACK_5MIN, min_periods=VOLUME_LOOKBACK_5MIN).max().to_numpy(dtype=float)
    c_vol_brk = ~np.isnan(vol_max_prior) & (volume5 > vol_max_prior)
    c_vol_floor = volume5 > MIN_VOLUME_5MIN

    day_p = price_df.index.to_period('D')
    week_p = price_df.index.to_period('W-FRI')
    d_ohlc = price_df.groupby(day_p).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    w_ohlc = price_df.groupby(week_p).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    _, d_r2 = _compute_pivot_r2(d_ohlc)
    _, w_r2 = _compute_pivot_r2(w_ohlc)
    d_r2_5 = d_r2.reindex(day_p).to_numpy(dtype=float)
    w_r2_5 = w_r2.reindex(week_p).to_numpy(dtype=float)
    c_d_r2 = ~np.isnan(d_r2_5) & (close5 > d_r2_5)
    c_w_r2 = ~np.isnan(w_r2_5) & (close5 > w_r2_5)

    p15 = price_df.index.floor('15min')
    o15 = price_df.groupby(p15).agg(close=('close', 'last'), volume=('volume', 'sum'))
    obv15 = pd.Series(compute_obv(o15['close'].to_numpy(float), o15['volume'].to_numpy(float)), index=o15.index)
    if OBV_EXCLUDE_CURRENT_BAR:
        obv_max = obv15.shift(1).rolling(OBV_LOOKBACK_15MIN, min_periods=OBV_LOOKBACK_15MIN).max()
    else:
        obv_max = obv15.rolling(OBV_LOOKBACK_15MIN, min_periods=OBV_LOOKBACK_15MIN).max()
    c_obv = (obv15 >= obv_max).reindex(p15).to_numpy()
    c_obv = np.where(pd.isna(c_obv), False, c_obv).astype(bool)

    n = len(close5)
    on = np.ones(n, dtype=bool)
    signal = ((c_vol_brk if USE_VOL_BREAKOUT else on)
              & (c_w_r2 if USE_WEEKLY_R2 else on)
              & (c_d_r2 if USE_DAILY_R2 else on)
              & (c_vol_floor if USE_VOL_FLOOR else on)
              & (c_obv if USE_OBV_15M else on))
    _log(f"   scan bars passing -> VolBreakout={int(c_vol_brk.sum())} WeeklyR2={int(c_w_r2.sum())} "
         f"DailyR2={int(c_d_r2.sum())} VolFloor={int(c_vol_floor.sum())} OBV15={int(c_obv.sum())} "
         f"ALL={int(signal.sum())}")
    debug = {
        'Vol_Max_Prior_300_5min': vol_max_prior,
        'Cond_Volume_Breakout': c_vol_brk,
        'Daily_R2': d_r2_5,
        'Weekly_R2': w_r2_5,
        'Cond_Above_Daily_R2': c_d_r2,
        'Cond_Above_Weekly_R2': c_w_r2,
        'Cond_Volume_Floor': c_vol_floor,
        'Cond_OBV_15min_Breakout': c_obv,
    }
    return signal, debug


# ============================================================
# STAGE 2 - TRADE SIMULATION (state machine on 5-min bars)
# ============================================================
IDLE, WAIT_15M, WAIT_BRK, STOP_PENDING, IN_TRADE = range(5)


def simulate_trades(price_df: pd.DataFrame, scan: np.ndarray, rsi: np.ndarray, vwap: np.ndarray, date_strs=None):
    n = len(price_df)
    idx = price_df.index
    opn = price_df['open'].to_numpy(float)
    high = price_df['high'].to_numpy(float)
    low = price_df['low'].to_numpy(float)
    close = price_df['close'].to_numpy(float)
    day = idx.normalize()
    tod = idx.time
    if date_strs is None:
        date_strs = idx.astype(str)

    bucket = idx.floor('15min')
    bucket_high = pd.Series(high, index=idx).groupby(bucket).max()

    is_eod = np.array([tod[i] >= SQUARE_OFF_TIME or (i + 1 < n and day[i + 1] != day[i])
                       for i in range(n)])
    no_new = np.array([t >= SQUARE_OFF_TIME for t in tod])

    long_entry = np.zeros(n, dtype=bool)
    tp_arr = np.full(n, np.nan)
    setup_high_arr = np.full(n, np.nan)
    brk_arr = np.zeros(n, dtype=bool)
    stop_arr = np.full(n, np.nan)
    sl_arr = np.full(n, np.nan)

    trades = []
    state = IDLE
    setup_day = b_start = b_end = None
    level = stop = entry = tp = sl = None
    e_idx = None
    lo = hi = None

    def close_trade(i, px, reason, is_open=False):
        trades.append({
            "entry_date": str(date_strs[e_idx]),
            "entry_price": round(float(entry), 2),
            "exit_date": str(date_strs[i]),
            "exit_price": round(float(px), 2),
            "exit_reason": reason,
            "mae_pct": round((lo - entry) / entry * 100, 2),
            "mfe_pct": round((hi - entry) / entry * 100, 2),
            "is_open": bool(is_open),
        })

    for i in range(n):
        # Setups never carry into the next day
        if state in (WAIT_15M, WAIT_BRK, STOP_PENDING) and day[i] != setup_day:
            state = IDLE

        # 1) Pending buy-stop: fill, or re-arm on a newer breakout candle
        if state == STOP_PENDING:
            if no_new[i]:
                state = IDLE
            elif high[i] >= stop:
                entry = max(opn[i], stop)
                tp = entry * (1 + TP_PCT / 100.0)
                sl = None
                e_idx = i
                lo, hi = min(entry, close[i]), high[i]
                long_entry[i] = True
                tp_arr[i] = TP_PCT
                state = IN_TRADE
            elif close[i] > level and rsi[i] > RSI_MIN_BREAKOUT:
                stop = high[i]
                brk_arr[i] = True

        # 2) 15-min candle containing the signal has closed -> mark its high
        if state == WAIT_15M and idx[i] >= b_end:
            level = float(bucket_high.loc[b_start])
            state = WAIT_BRK

        # 3) Wait for 5-min close above marked high with RSI > 80
        if state == WAIT_BRK:
            setup_high_arr[i] = level
            if no_new[i]:
                state = IDLE
            elif close[i] > level and rsi[i] > RSI_MIN_BREAKOUT:
                stop = high[i]
                brk_arr[i] = True
                state = STOP_PENDING

        if state == STOP_PENDING:
            stop_arr[i] = stop
            setup_high_arr[i] = level

        # 4) Manage open trade
        if state == IN_TRADE:
            if i != e_idx:
                lo, hi = min(lo, low[i]), max(hi, high[i])
            exited = False
            if i != e_idx and sl is not None and low[i] <= sl:
                px = opn[i] if opn[i] < sl else sl
                close_trade(i, px, "SL (gap below VWAP-candle low)" if opn[i] < sl else "SL (VWAP-candle low)")
                exited = True
            elif high[i] >= tp:
                px = opn[i] if (i != e_idx and opn[i] > tp) else tp
                close_trade(i, px, "TP 3%")
                exited = True
            elif is_eod[i]:
                close_trade(i, close[i], "EOD Square-off")
                exited = True
            elif i == n - 1:
                close_trade(i, close[i], "Open", is_open=True)
                exited = True

            if exited:
                state = IDLE
            else:
                if not np.isnan(vwap[i]) and close[i] < vwap[i]:
                    sl = low[i]            # move SL to this candle's low
                if sl is not None:
                    sl_arr[i] = sl

        # 5) New scan signal starts a setup (only when idle)
        if state == IDLE and scan[i] and not no_new[i]:
            b_start = bucket[i]
            b_end = b_start + pd.Timedelta(minutes=15)
            setup_day = day[i]
            state = WAIT_15M

    extra = {
        'Setup_15m_High': setup_high_arr,
        'Breakout_Candle': brk_arr,
        'Buy_Stop_Level': stop_arr,
        'Active_SL': sl_arr,
    }
    return trades, long_entry, tp_arr, extra


# ============================================================
# MAIN
# ============================================================
def _empty(df, reason=""):
    """Empty result in the same shape as the working template (tp/sl filled, not NaN)."""
    df = df.copy()
    if reason:
        df['Gate_Fail_Reason'] = reason
        _log(f"[GATE] {reason}")
    return {
        "trades": [],
        "long_entry": pd.Series(False, index=df.index),
        "entries": pd.Series(False, index=df.index),
        "signal": pd.Series(False, index=df.index),
        "tp_pct": pd.Series(TP_PCT, index=df.index),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=df.index),
        "df": df,
    }


def _call_helper(name, *args, **kwargs):
    """Same lookup order as the working template: sandbox globals -> app module."""
    fn = globals().get(name)
    if callable(fn):
        try:
            return fn(*args, **kwargs)
        except Exception:
            pass
    try:
        mod = __import__('app')
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn(*args, **kwargs)
    except Exception:
        pass
    return None


def _get_symbol(df):
    for c in ['symbol', 'Symbol', 'SYMBOL', 'ticker', 'Ticker']:
        if c in df.columns:
            s_vals = df[c].dropna()
            if not s_vals.empty:
                return str(s_vals.iloc[-1]).upper().replace('.NS', '').strip()
    if hasattr(df, 'attrs') and 'symbol' in df.attrs:
        return str(df.attrs['symbol']).upper().replace('.NS', '').strip()
    return None


def _get_market_cap(df, symbol):
    for c in df.columns:
        if str(c).lower() == 'market_cap_cr':
            s_vals = pd.to_numeric(df[c], errors='coerce').dropna()
            if not s_vals.empty:
                return float(s_vals.iloc[-1])
    m = _call_helper('get_market_cap_cr', symbol, fetch_online=False) if symbol else None
    if m is None and symbol:
        f = _call_helper('get_stock_fundamentals', symbol, fetch_online=False) or {}
        m = f.get('marketCapCr')
    try:
        return float(m) if m is not None and not pd.isna(m) else None
    except (TypeError, ValueError):
        return None


def backtest(df: pd.DataFrame) -> dict:
    df = df.copy()

    # ---- Column clean-up (one source per field -> no duplicate-key errors) ----
    clean_cols = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow in ['open', 'high', 'low', 'close', 'volume', 'prev_close', 'date', 'market_cap_cr', 'symbol'] \
                and clow not in clean_cols.values():
            clean_cols[c] = clow
    price_df = df[list(clean_cols.keys())].rename(columns=clean_cols)
    if 'date' in price_df.columns:
        price_df.index = pd.to_datetime(price_df['date'])
    elif isinstance(df.index, pd.DatetimeIndex):
        price_df.index = df.index
    else:
        price_df.index = pd.to_datetime(price_df.index)
    price_df = price_df[~price_df.index.duplicated(keep='last')].sort_index()
    for col in ('open', 'high', 'low', 'close', 'volume'):
        if col not in price_df.columns:
            return _empty(price_df, f"missing column '{col}'")
        price_df[col] = pd.to_numeric(price_df[col], errors='coerce')
    price_df = price_df.dropna(subset=['open', 'high', 'low', 'close'])

    # Date strings exactly as the sandbox supplied them (so trade dates match its rows)
    if 'date' in price_df.columns:
        date_strs = price_df['date'].astype(str).to_numpy()
    else:
        date_strs = price_df.index.astype(str).to_numpy()
        price_df['date'] = date_strs

    symbol = _get_symbol(df)

    # ---- Timeframe check: this strategy needs 5-minute bars ----
    if len(price_df) > 5:
        spacing = pd.Series(price_df.index).diff().median()
        if spacing > pd.Timedelta(minutes=5):
            return _empty(price_df, f"{symbol}: bar spacing {spacing} - run this on the 5-min timeframe")

    # ---- History check: 300-bar volume lookback + 200 x 15-min OBV lookback ----
    min_bars = max(VOLUME_LOOKBACK_5MIN, OBV_LOOKBACK_15MIN * 3) + 10
    if len(price_df) < min_bars:
        return _empty(price_df, f"{symbol}: only {len(price_df)} bars, need {min_bars}+ (~{min_bars // 75 + 1} trading days)")

    # ---- Market cap gate ----
    market_cap = _get_market_cap(df, symbol)
    if MIN_MARKET_CAP_CR > 0 and (market_cap is None or market_cap <= MIN_MARKET_CAP_CR):
        return _empty(price_df, f"{symbol}: market cap {market_cap} <= {MIN_MARKET_CAP_CR} (or unavailable)")

    # ---- Stage 1: scan ----
    _log(f"[{symbol}] bars={len(price_df)} from {price_df.index[0]} to {price_df.index[-1]}")
    scan, scan_dbg = _scan_signal(price_df)

    # ---- Stage 2: entry / exit ----
    rsi = compute_rsi(price_df['close'], RSI_LEN)
    vwap = compute_session_vwap(price_df)
    trades, long_entry, tp_arr, extra = simulate_trades(price_df, scan, rsi, vwap, date_strs)

    _log(f"[{symbol}] scan_hits={int(scan.sum())} breakouts={int(extra['Breakout_Candle'].sum())} "
         f"trades={len(trades)}")

    out_df = price_df.copy()
    for k, v in scan_dbg.items():
        out_df[k] = v
    out_df['Market_Cap_Cr'] = market_cap
    out_df['Scan_Pass'] = scan
    out_df['RSI_5m'] = np.round(rsi, 2)
    out_df['VWAP'] = np.round(vwap, 2)
    for k, v in extra.items():
        out_df[k] = v
    out_df['Long_Entry'] = long_entry
    out_df['Date'] = date_strs

    idx = price_df.index
    return {
        "trades": trades,
        "long_entry": pd.Series(long_entry, index=idx),
        "entries": pd.Series(long_entry, index=idx),
        "signal": pd.Series(scan, index=idx),
        "tp_pct": pd.Series(tp_arr, index=idx).fillna(TP_PCT),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=idx),
        "df": out_df,
    }


screen = backtest
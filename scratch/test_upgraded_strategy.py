import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '.')
from app import validate_backtest_code

STRATEGY_CODE = '''"""
Weekly Yearly-R1 Breakout Strategy (RSI > 80 + Next Bar Breakout + 100% TP & 30 EMA Trailing Exit)
===================================================================================================
Timeframe: WEEKLY candles (automatically resamples daily data to weekly W-FRI).

STRATEGY RULES:

1. YEARLY PIVOT & R1:
   Computed from the PRIOR completed calendar year's High, Low, and Close:
       Pivot = (High_prev_year + Low_prev_year + Close_prev_year) / 3
       R1    = 2 * Pivot - Low_prev_year
   Held constant across all weekly candles of the current calendar year.

2. BUY QUALIFICATION CANDLE:
   A weekly candle qualifies as a candidate when:
   - High crosses above that calendar year's Yearly R1:
     (high[i] > r1[i] and high[i-1] <= r1[i-1]).
   - Volume confirmation: that same week's volume exceeds the highest weekly volume
     in the trailing VOLUME_LOOKBACK_WEEKS (52 weeks / 1 year).
   - RSI filter: Weekly 14-period RSI must be strictly above 80 (RSI > 80.0).

3. ENTRY TRIGGER (Next Candle Breaks High):
   - We do not buy immediately on the qualifying candle; we place a buy stop at the
     HIGH of this qualifying candle.
   - Entry triggers when the NEXT immediate weekly candle breaks above this high
     (high[i+1] > qualifying_high).
   - Entry Price = HIGH of the qualifying candle (or open[i+1] if gapped above).
   - Arms the 15-candle tracking window from this initial buy.

4. 2-CANDLE EARLY EXIT RULE:
   - Once bought, if either one of the next immediate two candles (bar 1 or bar 2 after buy)
     closes below Yearly R1 (close < r1):
       * Exit immediately on that candle's close (Exit Price = Close).
       * Exit Reason = "Early Exit (Close Below Yearly R1 on bar N)".
       * Arms the 15-candle Re-entry Tracking Window.

5. RE-ENTRY WATCHING WINDOW (Up to 15 candles from initial buy):
   - After an early exit, wait for a weekly candle to CLOSE above Yearly R1 again (close > r1).
   - NO volume confirmation is required for this re-entry.
   - Re-entry Price = Close of that qualifying candle.
   - If 15 candles from the initial buy candle elapse without re-entry, the stock is DROPPED.
   - A fresh position is only taken in the future when ALL initial buy conditions are met again.

6. TARGET PROFIT & EXIT CRITERIA (Established Trades):
   - Criteria 1: Target Profit of 100% (+100.0% gain from entry price: tp_price = entry_price * 2.0).
     Triggers intrabar when high >= tp_price.
   - Criteria 2: 30 EMA Breakdown Exit:
     When a weekly candle closes below the 30-period EMA (close < ema30), its low becomes the armed low.
     If the low of this candle gets broken by a subsequent candle (low < armed_low), exit immediately!
     (If price closes back above 30 EMA without breaking the low, the breakdown is disarmed).

FUNDAMENTAL GATE:
   Configurable pre-filter (Market Cap, ROE, PE, Debt/Equity) - disabled by default (0).
"""

import numpy as np
import pandas as pd

# ============================================================
# CONFIG - FUNDAMENTAL PRE-FILTER GATE (0 / False disables a check)
# ============================================================
MIN_MARKET_CAP_CR = 0
MIN_ROE = 0.0
MAX_PE = 0.0
MAX_DEBT_TO_EQUITY = 0.0

# ============================================================
# CONFIG - SIGNAL / VOLUME / RSI / EXITS
# ============================================================
VOLUME_LOOKBACK_WEEKS = 52       # ~1 trading year of weekly bars
VOLUME_CONFIRM_MODE = "max"      # "max" = signal week volume must exceed highest weekly volume
VOLUME_CONFIRM_MULT = 1.0        # multiplier applied to baseline
RSI_PERIOD = 14                  # standard Wilder RSI period
MIN_RSI = 80.0                   # candle qualifying for a buy must have RSI > 80
EMA_PERIOD = 30                  # weekly close EMA used for trend trailing exit
TP_PCT = 100.0                   # fixed target profit in % (100% profit target)
DEFAULT_SL_PCT = 10.0            # fallback stop loss % for scalar consumers
MAX_HOLD_BARS = 250              # safety cap (weeks) so a trade cannot run indefinitely
MAX_REENTRY_WAIT_BARS = 15       # maximum candles to track for re-entry from initial buy


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Standard Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(avg_gain != 0, 0.0)
    return rsi.fillna(50.0)


def _compute_yearly_pivot_r1(df: pd.DataFrame):
    """Yearly Pivot & R1 from the PRIOR completed calendar year's OHLC,
    held constant across the current year's weekly rows."""
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


def _volume_confirmed(volume: np.ndarray, i: int) -> bool:
    """Checks that week i's volume exceeds the trailing VOLUME_LOOKBACK_WEEKS baseline."""
    start = max(0, i - VOLUME_LOOKBACK_WEEKS)
    if start >= i:
        return False
    window = volume[start:i]
    baseline = window.max() if VOLUME_CONFIRM_MODE == "max" else window.mean()
    return volume[i] > baseline * VOLUME_CONFIRM_MULT


def simulate_trades(df: pd.DataFrame):
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)
    volume = df['volume'].to_numpy(dtype=float)
    dates = df['date'].astype(str).to_numpy()
    n = len(close)

    _, r1 = _compute_yearly_pivot_r1(df)
    rsi = compute_rsi(pd.Series(close), RSI_PERIOD).to_numpy()
    ema30 = pd.Series(close).ewm(span=EMA_PERIOD, adjust=False).mean().to_numpy()

    long_entry = np.zeros(n, dtype=bool)
    signal = np.zeros(n, dtype=bool)
    tp_pct_arr = np.full(n, np.nan)
    sl_pct_arr = np.full(n, DEFAULT_SL_PCT)
    trades = []

    state = "IDLE"  # "IDLE", "AWAITING_BREAKOUT", "IN_TRADE", "WAITING_FOR_REENTRY"
    qualifying_high = None

    initial_buy_idx = None
    tracking_deadline_idx = None

    trade_entry_idx = None
    entry_price = None
    tp_price = None
    trade_type = "INITIAL"
    ema30_armed_low = None
    mae = 0.0
    mfe = 0.0

    i = 1
    while i < n:
        if np.isnan(r1[i]):
            i += 1
            continue

        if state == "IDLE":
            # Check Buy Qualification:
            # 1. High crosses above Yearly R1
            # 2. Volume confirmation
            # 3. Weekly RSI > 80
            crossed_now = high[i] > r1[i]
            was_below = high[i - 1] <= r1[i - 1] if not np.isnan(r1[i - 1]) else False
            vol_ok = _volume_confirmed(volume, i)
            rsi_ok = rsi[i] > MIN_RSI

            if crossed_now and was_below and vol_ok and rsi_ok:
                signal[i] = True
                qualifying_high = high[i]
                state = "AWAITING_BREAKOUT"
            i += 1
            continue

        elif state == "AWAITING_BREAKOUT":
            # We buy at the high of the qualifying candle when the NEXT candle breaks the high
            if high[i] > qualifying_high:
                trade_entry_idx = i
                entry_price = qualifying_high if open_[i] <= qualifying_high else open_[i]
                tp_price = entry_price * (1.0 + TP_PCT / 100.0)
                trade_type = "INITIAL"
                state = "IN_TRADE"
                ema30_armed_low = None

                long_entry[i] = True
                tp_pct_arr[i] = TP_PCT

                initial_buy_idx = i
                tracking_deadline_idx = initial_buy_idx + MAX_REENTRY_WAIT_BARS

                mae = (entry_price - low[i]) / entry_price * 100.0
                mfe = (high[i] - entry_price) / entry_price * 100.0

                # Check intrabar TP on entry candle itself
                if high[i] >= tp_price:
                    exit_p = tp_price if open_[i] <= tp_price else open_[i]
                    trades.append({
                        "entry_date": dates[i],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates[i],
                        "exit_price": round(float(exit_p), 2),
                        "exit_reason": "Target Profit (100% Same Bar)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
                        "trade_type": trade_type,
                    })
                    state = "IDLE"
                i += 1
                continue
            else:
                # Next candle failed to break high -> setup lapsed back to IDLE
                state = "IDLE"
                # Re-evaluate candle i as IDLE
                continue

        elif state == "IN_TRADE":
            bars_in_trade = i - trade_entry_idx
            mae = max(mae, (entry_price - low[i]) / entry_price * 100.0)
            mfe = max(mfe, (high[i] - entry_price) / entry_price * 100.0)

            # Safety cap
            if bars_in_trade >= MAX_HOLD_BARS:
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates[i],
                    "exit_price": round(float(close[i]), 2),
                    "exit_reason": "OPEN_TIMEOUT",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": True,
                    "trade_type": trade_type,
                })
                state = "IDLE"
                i += 1
                continue

            # Check next immediate two candles (bar 1 and bar 2 after buy):
            if bars_in_trade in (1, 2):
                # 1. 100% Target Profit
                if high[i] >= tp_price:
                    exit_p = tp_price if open_[i] <= tp_price else open_[i]
                    trades.append({
                        "entry_date": dates[trade_entry_idx],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates[i],
                        "exit_price": round(float(exit_p), 2),
                        "exit_reason": "Target Profit (100%)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
                        "trade_type": trade_type,
                    })
                    state = "IDLE"
                    i += 1
                    continue

                # 2. Early Exit if candle closes below Yearly R1
                if close[i] < r1[i]:
                    exit_price = close[i]
                    trades.append({
                        "entry_date": dates[trade_entry_idx],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates[i],
                        "exit_price": round(float(exit_price), 2),
                        "exit_reason": f"Early Exit (Close Below Yearly R1 on bar {bars_in_trade})",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
                        "trade_type": trade_type,
                    })
                    if i < tracking_deadline_idx:
                        state = "WAITING_FOR_REENTRY"
                    else:
                        state = "IDLE"
                    i += 1
                    continue

            # Bar 3 onwards (survived bars 1 & 2 without closing below R1):
            # Check 1: Target Profit of 100%
            if high[i] >= tp_price:
                exit_p = tp_price if open_[i] <= tp_price else open_[i]
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates[i],
                    "exit_price": round(float(exit_p), 2),
                    "exit_reason": "Target Profit (100%)",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False,
                    "trade_type": trade_type,
                })
                state = "IDLE"
                i += 1
                continue

            # Check 2: 30 EMA Breakdown Exit
            # "if the candle closes below 30 EMA and the low of this candle get breaken"
            if ema30_armed_low is not None:
                if low[i] < ema30_armed_low:
                    exit_p = ema30_armed_low if open_[i] >= ema30_armed_low else open_[i]
                    trades.append({
                        "entry_date": dates[trade_entry_idx],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates[i],
                        "exit_price": round(float(exit_p), 2),
                        "exit_reason": "Exit (Close Below 30 EMA and Low Broken)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
                        "trade_type": trade_type,
                    })
                    state = "IDLE"
                    ema30_armed_low = None
                    i += 1
                    continue
                else:
                    if close[i] < ema30[i]:
                        ema30_armed_low = min(ema30_armed_low, low[i])
                    else:
                        ema30_armed_low = None
            else:
                if not np.isnan(ema30[i]) and close[i] < ema30[i]:
                    ema30_armed_low = low[i]

            i += 1
            continue

        elif state == "WAITING_FOR_REENTRY":
            if i > tracking_deadline_idx:
                # 15 candles done: drop tracking
                state = "IDLE"
                continue

            # Candle closes above Yearly R1 again (no volume confirmation required)
            if close[i] > r1[i]:
                long_entry[i] = True
                signal[i] = True
                tp_pct_arr[i] = TP_PCT

                trade_entry_idx = i
                entry_price = close[i]
                tp_price = entry_price * (1.0 + TP_PCT / 100.0)
                trade_type = "REENTRY"
                state = "IN_TRADE"
                ema30_armed_low = None
                mae = (entry_price - low[i]) / entry_price * 100.0
                mfe = (high[i] - entry_price) / entry_price * 100.0

                if high[i] >= tp_price:
                    trades.append({
                        "entry_date": dates[i],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates[i],
                        "exit_price": round(float(tp_price), 2),
                        "exit_reason": "Target Profit (100% Same Bar)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
                        "trade_type": trade_type,
                    })
                    state = "IDLE"
            i += 1
            continue

    if state == "IN_TRADE":
        trades.append({
            "entry_date": dates[trade_entry_idx],
            "entry_price": round(float(entry_price), 2),
            "exit_date": dates[-1],
            "exit_price": round(float(close[-1]), 2),
            "exit_reason": "End of Data",
            "mae_pct": round(float(mae), 2),
            "mfe_pct": round(float(mfe), 2),
            "is_open": True,
            "trade_type": trade_type,
        })

    return trades, long_entry, signal, tp_pct_arr, sl_pct_arr


def _ensure_weekly_df(df: pd.DataFrame) -> pd.DataFrame:
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


def backtest(df: pd.DataFrame) -> dict:
    df = _ensure_weekly_df(df)
    n = len(df)
    empty_res = {
        "trades": [],
        "long_entry": pd.Series(False, index=df.index),
        "entries": pd.Series(False, index=df.index),
        "signal": pd.Series(False, index=df.index),
        "tp_pct": pd.Series(TP_PCT, index=df.index),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=df.index),
        "df": df
    }

    if n < (VOLUME_LOOKBACK_WEEKS + EMA_PERIOD + 5):
        return empty_res

    # Fundamental pre-filter gate
    def _last(col):
        if col in df.columns and pd.notna(df[col].iloc[-1]):
            return float(df[col].iloc[-1])
        return None

    market_cap = _last("Market_Cap_Cr")
    roe = _last("ROE")
    pe = _last("PE")
    de = _last("Debt_To_Equity")

    if MIN_MARKET_CAP_CR > 0 and (market_cap is None or market_cap < MIN_MARKET_CAP_CR):
        return empty_res
    if MIN_ROE > 0 and (roe is None or roe < MIN_ROE):
        return empty_res
    if MAX_PE > 0 and (pe is None or pe <= 0 or pe > MAX_PE):
        return empty_res
    if MAX_DEBT_TO_EQUITY > 0 and (de is None or de > MAX_DEBT_TO_EQUITY):
        return empty_res

    trades, long_entry_arr, signal_arr, tp_pct_arr, sl_pct_arr = simulate_trades(df)

    return {
        "trades": trades,
        "long_entry": pd.Series(long_entry_arr, index=df.index),
        "entries": pd.Series(long_entry_arr, index=df.index),
        "signal": pd.Series(signal_arr, index=df.index),
        "tp_pct": pd.Series(tp_pct_arr, index=df.index).fillna(TP_PCT),
        "sl_pct": pd.Series(sl_pct_arr, index=df.index).fillna(DEFAULT_SL_PCT),
        "df": df
    }

screen = backtest
'''

is_valid, err_msg, func = validate_backtest_code(STRATEGY_CODE)
print(f"Validation Result: is_valid={is_valid}, err_msg={err_msg}")

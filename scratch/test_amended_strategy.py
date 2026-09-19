"""
Test and validate amended strategy logic before replacing in production files.
"""

import os
import glob
import pandas as pd
import numpy as np

MIN_MARKET_CAP_CR = 0.0
MIN_ROE = 0.0
MAX_PE = 0.0
MAX_DEBT_TO_EQUITY = 0.0

DAILY_RSI_PERIOD = 14
DAILY_RSI_THRESHOLD = 85.0

WEEKLY_EMA_FAST = 10
WEEKLY_EMA_MID = 30
WEEKLY_EMA_SLOW = 40

TP_PCT = 100.0
DEFAULT_SL_PCT = 10.0
MAX_HOLD_DAYS = 500

REQUIRE_WEEKLY_STACK_ON_R1_ENTRY = False
MAX_R1_TRIGGER_WAIT_DAYS = 0


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
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
    if 'date' in df.columns:
        year_period = pd.to_datetime(df['date']).dt.to_period('Y')
    elif isinstance(df.index, pd.DatetimeIndex):
        year_period = df.index.to_period('Y')
    else:
        year_period = pd.to_datetime(df.index).to_period('Y')

    yearly_ohlc = pd.DataFrame({
        'high': df['high'], 'low': df['low'], 'close': df['close'],
    }, index=df.index).groupby(year_period).agg(
        high=('high', 'max'), low=('low', 'min'), close=('close', 'last')
    )
    yearly_pivot = (yearly_ohlc['high'] + yearly_ohlc['low'] + yearly_ohlc['close']) / 3.0
    yearly_r1 = 2.0 * yearly_pivot - yearly_ohlc['low']

    pivot_for_row = year_period.map(yearly_pivot.shift(1)).to_numpy(dtype=float)
    r1_for_row = year_period.map(yearly_r1.shift(1)).to_numpy(dtype=float)
    return pivot_for_row, r1_for_row


def _prepare_data(df: pd.DataFrame):
    df = df.copy()
    clean_cols = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow in ['open', 'high', 'low', 'close', 'volume', 'date', 'market_cap_cr', 'symbol'] and clow not in clean_cols.values():
            clean_cols[c] = clow
    df_clean = df[list(clean_cols.keys())].rename(columns=clean_cols)

    if 'date' in df_clean.columns and not isinstance(df_clean.index, pd.DatetimeIndex):
        df_clean.index = pd.to_datetime(df_clean['date'])
    elif not isinstance(df_clean.index, pd.DatetimeIndex):
        df_clean.index = pd.to_datetime(df_clean.index)
    df_clean = df_clean.sort_index()

    # Resample daily to weekly Friday bars
    w_df = df_clean.resample('W-FRI').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna(subset=['close'])

    w_df['w_ema10'] = w_df['close'].ewm(span=WEEKLY_EMA_FAST, adjust=False).mean()
    w_df['w_ema30'] = w_df['close'].ewm(span=WEEKLY_EMA_MID, adjust=False).mean()
    w_df['w_ema40'] = w_df['close'].ewm(span=WEEKLY_EMA_SLOW, adjust=False).mean()
    w_df['w_stacked'] = (w_df['w_ema10'] > w_df['w_ema30']) & (w_df['w_ema30'] > w_df['w_ema40'])
    w_df['w_close_below_30ema'] = w_df['close'] < w_df['w_ema30']

    # Map weekly state lookahead-free using prior completed week
    w_period = df_clean.index.to_period('W-FRI')
    w_stacked_shifted = w_df['w_stacked'].shift(1).to_period('W-FRI')
    w_ema30_shifted = w_df['w_ema30'].shift(1).to_period('W-FRI')

    df_clean['weekly_ema_stacked'] = w_period.map(w_stacked_shifted).fillna(False).astype(bool)
    df_clean['weekly_ema30'] = w_period.map(w_ema30_shifted).to_numpy(dtype=float)

    # Daily RSI
    df_clean['daily_rsi'] = compute_rsi(df_clean['close'], DAILY_RSI_PERIOD)
    df_clean['rsi_crossed_85'] = (df_clean['daily_rsi'] > DAILY_RSI_THRESHOLD) & (df_clean['daily_rsi'].shift(1) <= DAILY_RSI_THRESHOLD)

    # Yearly R1
    piv, r1 = _compute_yearly_pivot_r1(df_clean)
    df_clean['yearly_pivot'] = piv
    df_clean['yearly_r1'] = r1

    df_clean['date_str'] = df_clean.index.strftime('%Y-%m-%d')
    w_df['date_str'] = w_df.index.strftime('%Y-%m-%d')

    return df_clean, w_df


def simulate_trades(df: pd.DataFrame):
    df_clean, w_df = _prepare_data(df)
    n = len(df_clean)
    if n < 60:
        return [], np.zeros(n, dtype=bool), np.zeros(n, dtype=bool), np.full(n, np.nan), np.full(n, np.nan)

    high = df_clean['high'].to_numpy(dtype=float)
    low = df_clean['low'].to_numpy(dtype=float)
    close = df_clean['close'].to_numpy(dtype=float)
    open_ = df_clean['open'].to_numpy(dtype=float)
    dates = df_clean['date_str'].to_numpy()
    d_indices = df_clean.index

    rsi_cross = df_clean['rsi_crossed_85'].to_numpy(dtype=bool)
    weekly_stacked = df_clean['weekly_ema_stacked'].to_numpy(dtype=bool)
    r1 = df_clean['yearly_r1'].to_numpy(dtype=float)

    w_close = w_df['close'].to_numpy(dtype=float)
    w_low = w_df['low'].to_numpy(dtype=float)
    w_ema30 = w_df['w_ema30'].to_numpy(dtype=float)
    w_indices = w_df.index

    long_entry = np.zeros(n, dtype=bool)
    signal = np.zeros(n, dtype=bool)
    tp_pct_arr = np.full(n, np.nan)
    sl_pct_arr = np.full(n, DEFAULT_SL_PCT)
    trades = []

    state = "IDLE"  # "IDLE", "AWAITING_R1_CLOSE", "IN_TRADE"
    r1_trigger_idx = None

    trade_entry_idx = None
    entry_price = None
    tp_price = None
    armed_sl_low = None
    last_checked_w_idx = -1
    mae = 0.0
    mfe = 0.0

    i = 1
    while i < n:
        cur_date = d_indices[i]

        # In trade: check weekly candle closes for 30 EMA breakdown
        if state == "IN_TRADE":
            w_past = np.where(w_indices <= cur_date)[0]
            if len(w_past) > 0:
                cur_w_idx = w_past[-1]
                if cur_w_idx > last_checked_w_idx and cur_w_idx >= 0:
                    if w_close[cur_w_idx] < w_ema30[cur_w_idx]:
                        armed_sl_low = w_low[cur_w_idx] if armed_sl_low is None else min(armed_sl_low, w_low[cur_w_idx])
                    else:
                        armed_sl_low = None
                    last_checked_w_idx = cur_w_idx

            bars_in_trade = i - trade_entry_idx
            mae = max(mae, (entry_price - low[i]) / entry_price * 100.0)
            mfe = max(mfe, (high[i] - entry_price) / entry_price * 100.0)

            # Safety hold timeout
            if bars_in_trade >= MAX_HOLD_DAYS:
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates[i],
                    "exit_price": round(float(close[i]), 2),
                    "exit_reason": "OPEN_TIMEOUT",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": True,
                })
                state = "IDLE"
                armed_sl_low = None
                i += 1
                continue

            # Criteria 1: 100% Target Profit (Intrabar)
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
                })
                state = "IDLE"
                armed_sl_low = None
                i += 1
                continue

            # Criteria 2: 30 EMA Breakdown Exit (low breaks armed low)
            if armed_sl_low is not None and low[i] < armed_sl_low:
                exit_p = armed_sl_low if open_[i] >= armed_sl_low else open_[i]
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates[i],
                    "exit_price": round(float(exit_p), 2),
                    "exit_reason": "Exit (Close Below 30 EMA and Low Broken)",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False,
                })
                state = "IDLE"
                armed_sl_low = None
                i += 1
                continue

            i += 1
            continue

        if state == "IDLE":
            # Signal check: Daily RSI crosses above 85 AND Weekly EMAs stacked (10 > 30 > 40)
            if rsi_cross[i] and weekly_stacked[i]:
                signal[i] = True

                # Check Yearly R1:
                # "when the daily candle crosses aboave RSI 85, it should be also above Yearly R1,
                #  if not then this becomes a buy trigger and we will buy only when a daily candle
                #  closes above the Yearly R1, we will buy at the high of this candle"
                if not np.isnan(r1[i]) and close[i] > r1[i]:
                    # Already above Yearly R1! Buy at high of this candle
                    trade_entry_idx = i
                    entry_price = high[i]
                    tp_price = entry_price * (1.0 + TP_PCT / 100.0)
                    long_entry[i] = True
                    tp_pct_arr[i] = TP_PCT

                    state = "IN_TRADE"
                    armed_sl_low = None
                    last_checked_w_idx = -1
                    mae = (entry_price - low[i]) / entry_price * 100.0
                    mfe = (high[i] - entry_price) / entry_price * 100.0

                    # Intrabar 100% TP check
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
                        })
                        state = "IDLE"
                else:
                    # Below or equal to Yearly R1 -> Armed Buy Trigger!
                    state = "AWAITING_R1_CLOSE"
                    r1_trigger_idx = i

            i += 1
            continue

        elif state == "AWAITING_R1_CLOSE":
            # If another RSI 85 cross occurs while awaiting, refresh trigger
            if rsi_cross[i] and weekly_stacked[i]:
                r1_trigger_idx = i

            # Check optional timeout
            if MAX_R1_TRIGGER_WAIT_DAYS > 0 and (i - r1_trigger_idx) >= MAX_R1_TRIGGER_WAIT_DAYS:
                state = "IDLE"
                i += 1
                continue

            # Check optional weekly stack requirement
            if REQUIRE_WEEKLY_STACK_ON_R1_ENTRY and not weekly_stacked[i]:
                state = "IDLE"
                i += 1
                continue

            # Check if a daily candle closes above Yearly R1:
            if not np.isnan(r1[i]) and close[i] > r1[i]:
                # We buy at the high of THIS candle!
                trade_entry_idx = i
                entry_price = high[i]
                tp_price = entry_price * (1.0 + TP_PCT / 100.0)
                long_entry[i] = True
                signal[i] = True
                tp_pct_arr[i] = TP_PCT

                state = "IN_TRADE"
                armed_sl_low = None
                last_checked_w_idx = -1
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
        })

    return trades, long_entry, signal, tp_pct_arr, sl_pct_arr


def backtest(df: pd.DataFrame) -> dict:
    df_clean, _ = _prepare_data(df)
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

    if n < 60:
        return empty_res

    trades, long_entry_arr, signal_arr, tp_pct_arr, sl_pct_arr = simulate_trades(df)

    return {
        "trades": trades,
        "long_entry": pd.Series(long_entry_arr, index=df_clean.index),
        "entries": pd.Series(long_entry_arr, index=df_clean.index),
        "signal": pd.Series(signal_arr, index=df_clean.index),
        "tp_pct": pd.Series(tp_pct_arr, index=df_clean.index).fillna(TP_PCT),
        "sl_pct": pd.Series(sl_pct_arr, index=df_clean.index).fillna(DEFAULT_SL_PCT),
        "df": df_clean
    }


# Test across sample stocks
test_symbols = ['TRENT', 'AJANTPHARM', 'BEL', 'RELIANCE', 'HAL']
for sym in test_symbols:
    p = f'data/adjusted_daily/{sym}.parquet'
    if os.path.exists(p):
        d = pd.read_parquet(p)
        res = backtest(d)
        print(f"=== {sym} ({len(res['trades'])} trades) ===")
        for t in res['trades']:
            print("  ", t)

import numpy as np
import pandas as pd

VOLUME_LOOKBACK_WEEKS = 52
VOLUME_CONFIRM_MODE = "max"
VOLUME_CONFIRM_MULT = 1.0
EMA_PERIOD = 10
TP_PCT = 50.0
MAX_HOLD_BARS = 250
MAX_REENTRY_WAIT_BARS = 15

def _compute_yearly_pivot_r1(df: pd.DataFrame):
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
    volume = df['volume'].to_numpy(dtype=float)
    dates = df['date'].astype(str).to_numpy()
    n = len(close)

    _, r1 = _compute_yearly_pivot_r1(df)
    ema = pd.Series(close).ewm(span=EMA_PERIOD, adjust=False).mean().to_numpy()

    long_entry = np.zeros(n, dtype=bool)
    signal = np.zeros(n, dtype=bool)
    tp_pct_arr = np.full(n, np.nan)
    sl_pct_arr = np.full(n, np.nan)
    trades = []

    state = "IDLE"  # IDLE, IN_TRADE, WAITING_FOR_REENTRY
    initial_buy_idx = None
    tracking_deadline_idx = None
    trade_entry_idx = None
    entry_price = None
    tp_price = None
    trade_label = "INITIAL"
    mae = 0.0
    mfe = 0.0

    i = 1
    while i < n:
        if np.isnan(r1[i]):
            i += 1
            continue

        if state == "IDLE":
            crossed_now = high[i] > r1[i]
            was_below = high[i - 1] <= r1[i - 1] if not np.isnan(r1[i - 1]) else False
            vol_ok = _volume_confirmed(volume, i)

            if crossed_now and was_below and vol_ok:
                signal[i] = True
                long_entry[i] = True
                tp_pct_arr[i] = TP_PCT

                initial_buy_idx = i
                tracking_deadline_idx = i + MAX_REENTRY_WAIT_BARS
                trade_entry_idx = i
                entry_price = high[i]
                tp_price = entry_price * (1.0 + TP_PCT / 100.0)
                trade_label = "INITIAL"
                state = "IN_TRADE"
                mae = (entry_price - low[i]) / entry_price * 100.0
                mfe = (high[i] - entry_price) / entry_price * 100.0

                if high[i] >= tp_price:
                    trades.append({
                        "entry_date": dates[i],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates[i],
                        "exit_price": round(float(tp_price), 2),
                        "exit_reason": "TP (Same Bar)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
                        "trade_type": trade_label
                    })
                    state = "IDLE"
            i += 1
            continue

        elif state == "IN_TRADE":
            bars_in_trade = i - trade_entry_idx
            mae = max(mae, (entry_price - low[i]) / entry_price * 100.0)
            mfe = max(mfe, (high[i] - entry_price) / entry_price * 100.0)

            # Safety max hold
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
                    "trade_type": trade_label
                })
                state = "IDLE"
                i += 1
                continue

            # First 2 immediate candles after entry (bars 1 and 2):
            if bars_in_trade in (1, 2):
                # 1. Target profit check
                if high[i] >= tp_price:
                    trades.append({
                        "entry_date": dates[trade_entry_idx],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates[i],
                        "exit_price": round(float(tp_price), 2),
                        "exit_reason": "TP",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
                        "trade_type": trade_label
                    })
                    state = "IDLE"
                    i += 1
                    continue

                # 2. Early exit: candle closes below Yearly R1
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
                        "trade_type": trade_label
                    })
                    if i < tracking_deadline_idx:
                        state = "WAITING_FOR_REENTRY"
                    else:
                        state = "IDLE"
                    i += 1
                    continue

            # Bar 3 onwards or survived bars 1 & 2 without closing below R1:
            # 1. Target profit check
            if high[i] >= tp_price:
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates[i],
                    "exit_price": round(float(tp_price), 2),
                    "exit_reason": "TP",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False,
                    "trade_type": trade_label
                })
                state = "IDLE"
                i += 1
                continue

            # 2. Stop loss check: Close below 10 EMA
            if not np.isnan(ema[i]) and close[i] < ema[i]:
                exit_price = low[i]
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates[i],
                    "exit_price": round(float(exit_price), 2),
                    "exit_reason": "SL (Close Below 10 EMA)",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False,
                    "trade_type": trade_label
                })
                state = "IDLE"
                i += 1
                continue

            i += 1
            continue

        elif state == "WAITING_FOR_REENTRY":
            # If 15 candles from initial buy candle are done -> drop tracking
            if i > tracking_deadline_idx:
                state = "IDLE"
                continue

            # Check if candle closes above R1 again (no volume confirmation needed)
            if close[i] > r1[i]:
                long_entry[i] = True
                signal[i] = True
                tp_pct_arr[i] = TP_PCT

                trade_entry_idx = i
                entry_price = close[i]
                tp_price = entry_price * (1.0 + TP_PCT / 100.0)
                trade_label = "REENTRY"
                state = "IN_TRADE"
                mae = (entry_price - low[i]) / entry_price * 100.0
                mfe = (high[i] - entry_price) / entry_price * 100.0

                if high[i] >= tp_price:
                    trades.append({
                        "entry_date": dates[i],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates[i],
                        "exit_price": round(float(tp_price), 2),
                        "exit_reason": "TP (Same Bar)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
                        "trade_type": trade_label
                    })
                    state = "IDLE"
            i += 1
            continue

    # If still in trade at end of data
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
            "trade_type": trade_label
        })

    return trades, long_entry, signal, tp_pct_arr, sl_pct_arr

print("Simulation function validated!")

import pandas as pd
import numpy as np
import os, glob
from strategies.weekly_yearly_r1_breakout import _ensure_weekly_df, _compute_yearly_pivot_r1, _volume_confirmed

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

def simulate_new_strategy(
    df: pd.DataFrame,
    min_rsi: float = 80.0,
    tp_pct: float = 100.0,
    ema_period: int = 30,
    max_wait_bars: int = 15
):
    w_df = _ensure_weekly_df(df)
    n = len(w_df)
    if n < 55:
        return [], w_df

    high = w_df['high'].to_numpy(dtype=float)
    low = w_df['low'].to_numpy(dtype=float)
    close = w_df['close'].to_numpy(dtype=float)
    open_ = w_df['open'].to_numpy(dtype=float)
    volume = w_df['volume'].to_numpy(dtype=float)
    dates = w_df['date'].astype(str).to_numpy()

    _, r1 = _compute_yearly_pivot_r1(w_df)
    rsi = compute_rsi(w_df['close'], 14).to_numpy()
    ema30 = pd.Series(close).ewm(span=ema_period, adjust=False).mean().to_numpy()

    trades = []

    # States:
    # 'IDLE': scanning for qualification candle
    # 'AWAITING_BREAKOUT': qualification candle found at q, watching candle q+1 to break high[q]
    # 'IN_TRADE': position is open
    # 'WAITING_FOR_REENTRY': exited early, watching for close > R1 within 15 candles from initial buy
    state = 'IDLE'
    qualifying_idx = None
    qualifying_high = None

    initial_buy_idx = None
    tracking_deadline_idx = None

    trade_entry_idx = None
    entry_price = None
    tp_price = None
    trade_type = 'INITIAL'
    ema30_armed_low = None
    mae = 0.0
    mfe = 0.0

    i = 1
    while i < n:
        if np.isnan(r1[i]):
            i += 1
            continue

        if state == 'IDLE':
            # Check Buy Qualification:
            # 1. High crosses above Yearly R1
            # 2. Volume confirmation (trailing 52 weeks max)
            # 3. Weekly RSI > 80
            crossed_now = high[i] > r1[i]
            was_below = high[i - 1] <= r1[i - 1] if not np.isnan(r1[i - 1]) else False
            vol_ok = _volume_confirmed(volume, i)
            rsi_ok = rsi[i] > min_rsi

            if crossed_now and was_below and vol_ok and rsi_ok:
                qualifying_idx = i
                qualifying_high = high[i]
                state = 'AWAITING_BREAKOUT'
            i += 1
            continue

        elif state == 'AWAITING_BREAKOUT':
            # Next candle (i = qualifying_idx + 1)
            # Check if this next candle breaks the qualifying candle's high
            if high[i] > qualifying_high:
                # BREAKOUT CONFIRMED! Buy executed on this candle
                trade_entry_idx = i
                entry_price = qualifying_high if open_[i] <= qualifying_high else open_[i]
                tp_price = entry_price * (1.0 + tp_pct / 100.0)
                trade_type = 'INITIAL'
                state = 'IN_TRADE'
                ema30_armed_low = None

                initial_buy_idx = i
                tracking_deadline_idx = initial_buy_idx + max_wait_bars

                mae = (entry_price - low[i]) / entry_price * 100.0
                mfe = (high[i] - entry_price) / entry_price * 100.0

                # Check if 100% TP reached on entry candle itself
                if high[i] >= tp_price:
                    trades.append({
                        'type': trade_type,
                        'entry_date': dates[i],
                        'entry_price': round(entry_price, 2),
                        'exit_date': dates[i],
                        'exit_price': round(tp_price, 2),
                        'exit_reason': 'Target Profit (100% Same Bar)',
                        'mae_pct': round(mae, 2),
                        'mfe_pct': round(mfe, 2),
                        'is_open': False
                    })
                    state = 'IDLE'
                i += 1
                continue
            else:
                # Next candle failed to break high -> setup lapsed
                state = 'IDLE'
                # Re-check candle i as IDLE candidate
                continue

        elif state == 'IN_TRADE':
            bars_in_trade = i - trade_entry_idx
            mae = max(mae, (entry_price - low[i]) / entry_price * 100.0)
            mfe = max(mfe, (high[i] - entry_price) / entry_price * 100.0)

            # Safety cap (weeks)
            if bars_in_trade >= 250:
                trades.append({
                    'type': trade_type,
                    'entry_date': dates[trade_entry_idx],
                    'entry_price': round(entry_price, 2),
                    'exit_date': dates[i],
                    'exit_price': round(close[i], 2),
                    'exit_reason': 'OPEN_TIMEOUT',
                    'mae_pct': round(mae, 2),
                    'mfe_pct': round(mfe, 2),
                    'is_open': True
                })
                state = 'IDLE'
                i += 1
                continue

            # First 2 immediate candles after buy (bars 1 and 2):
            if bars_in_trade in (1, 2):
                # 1. TP Check (100%)
                if high[i] >= tp_price:
                    exit_p = tp_price if open_[i] <= tp_price else open_[i]
                    trades.append({
                        'type': trade_type,
                        'entry_date': dates[trade_entry_idx],
                        'entry_price': round(entry_price, 2),
                        'exit_date': dates[i],
                        'exit_price': round(exit_p, 2),
                        'exit_reason': 'Target Profit (100%)',
                        'mae_pct': round(mae, 2),
                        'mfe_pct': round(mfe, 2),
                        'is_open': False
                    })
                    state = 'IDLE'
                    i += 1
                    continue

                # 2. Early Exit check: candle closes below Yearly R1
                if close[i] < r1[i]:
                    exit_p = close[i]
                    trades.append({
                        'type': trade_type,
                        'entry_date': dates[trade_entry_idx],
                        'entry_price': round(entry_price, 2),
                        'exit_date': dates[i],
                        'exit_price': round(exit_p, 2),
                        'exit_reason': f'Early Exit (Close Below Yearly R1 on bar {bars_in_trade})',
                        'mae_pct': round(mae, 2),
                        'mfe_pct': round(mfe, 2),
                        'is_open': False
                    })
                    if i < tracking_deadline_idx:
                        state = 'WAITING_FOR_REENTRY'
                    else:
                        state = 'IDLE'
                    i += 1
                    continue

            # Bar 3 onwards (survived bars 1 & 2 without closing below R1):
            # Check 1: Target Profit (100%)
            if high[i] >= tp_price:
                exit_p = tp_price if open_[i] <= tp_price else open_[i]
                trades.append({
                    'type': trade_type,
                    'entry_date': dates[trade_entry_idx],
                    'entry_price': round(entry_price, 2),
                    'exit_date': dates[i],
                    'exit_price': round(exit_p, 2),
                    'exit_reason': 'Target Profit (100%)',
                    'mae_pct': round(mae, 2),
                    'mfe_pct': round(mfe, 2),
                    'is_open': False
                })
                state = 'IDLE'
                i += 1
                continue

            # Check 2: 30 EMA Breakdown Exit
            # "if the candle closes below 30 EMA and the low of this candle get breaken"
            if ema30_armed_low is not None:
                # Check if low of the candle that closed below 30 EMA gets broken
                if low[i] < ema30_armed_low:
                    exit_p = ema30_armed_low if open_[i] >= ema30_armed_low else open_[i]
                    trades.append({
                        'type': trade_type,
                        'entry_date': dates[trade_entry_idx],
                        'entry_price': round(entry_price, 2),
                        'exit_date': dates[i],
                        'exit_price': round(exit_p, 2),
                        'exit_reason': 'Exit (Close Below 30 EMA and Low Broken)',
                        'mae_pct': round(mae, 2),
                        'mfe_pct': round(mfe, 2),
                        'is_open': False
                    })
                    state = 'IDLE'
                    ema30_armed_low = None
                    i += 1
                    continue
                else:
                    # Low was not broken on this bar.
                    if close[i] < ema30[i]:
                        # Ratchet or maintain the armed low
                        ema30_armed_low = min(ema30_armed_low, low[i])
                    else:
                        # Price closed back above 30 EMA -> trend intact, disarm!
                        ema30_armed_low = None
            else:
                # No armed low yet: check if this candle closes below 30 EMA
                if not np.isnan(ema30[i]) and close[i] < ema30[i]:
                    ema30_armed_low = low[i]

            i += 1
            continue

        elif state == 'WAITING_FOR_REENTRY':
            if i > tracking_deadline_idx:
                # 15 candles from initial buy are done -> drop tracking
                state = 'IDLE'
                continue

            # Check re-entry: candle closes above Yearly R1 (no volume confirmation needed)
            if close[i] > r1[i]:
                trade_entry_idx = i
                entry_price = close[i]
                tp_price = entry_price * (1.0 + tp_pct / 100.0)
                trade_type = 'REENTRY'
                state = 'IN_TRADE'
                ema30_armed_low = None
                mae = (entry_price - low[i]) / entry_price * 100.0
                mfe = (high[i] - entry_price) / entry_price * 100.0

                if high[i] >= tp_price:
                    trades.append({
                        'type': trade_type,
                        'entry_date': dates[i],
                        'entry_price': round(entry_price, 2),
                        'exit_date': dates[i],
                        'exit_price': round(tp_price, 2),
                        'exit_reason': 'Target Profit (100% Same Bar)',
                        'mae_pct': round(mae, 2),
                        'mfe_pct': round(mfe, 2),
                        'is_open': False
                    })
                    state = 'IDLE'
            i += 1
            continue

    if state == 'IN_TRADE':
        trades.append({
            'type': trade_type,
            'entry_date': dates[trade_entry_idx],
            'entry_price': round(entry_price, 2),
            'exit_date': dates[-1],
            'exit_price': round(close[-1], 2),
            'exit_reason': 'End of Data',
            'mae_pct': round(mae, 2),
            'mfe_pct': round(mfe, 2),
            'is_open': True
        })

    return trades, w_df

print("Script template ready for testing!")

"""
Daily Monthly-R3 Breakout above Yearly-R2 Strategy (Weekly 30 EMA Breakdown SL)
================================================================================
Timeframe: DAILY candles (expects Daily OHLCV data). Weekly aggregates & 30 EMA derived internally.
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).

STRATEGY CRITERIA & RULES:

1. PIVOT CALCULATIONS:
   - Monthly Pivots (PP & R3):
     Computed from the PRIOR completed calendar month's High, Low, Close:
       Monthly_PP = (High_month + Low_month + Close_month) / 3.0
       Monthly_R3 = Monthly_PP + 2.0 * (High_month - Low_month)
     Held constant across all daily candles of the current calendar month.
   - Yearly Pivots (PP & R2):
     Computed from the PRIOR completed calendar year's High, Low, Close:
       Yearly_PP = (High_year + Low_year + Close_year) / 3.0
       Yearly_R2 = Yearly_PP + (High_year - Low_year)
     Held constant across all daily candles of the current calendar year.

2. QUALIFYING CANDLE (Setup Trigger):
   - Fresh Breakout above Monthly R3:
     The daily candle must CLOSE strictly above Monthly R3:
       Close[i] > Monthly_R3[i]
     while the previous daily candle closed at or below its Monthly R3:
       Close[i-1] <= Monthly_R3[i-1]
   - Above Yearly R2 Alignment:
     When this candle has closed above Monthly R3, it must also be strictly above Yearly R2:
       Close[i] > Yearly_R2[i]
   - When qualified, this candle's HIGH is marked as the Buy-Stop trigger level:
       qualifying_high = High[i]

3. ENTRY TRIGGER & EXECUTION:
   - Next Candle Breakout:
     We place a buy-stop at the HIGH of the qualifying candle.
     When the next daily candle breaks above this qualifying high:
       High[i+1] > qualifying_high
     Entry triggers immediately!
   - Entry Price:
       entry_price = max(Open[i+1], qualifying_high)
     (Fills at Open if gapped above qualifying high, otherwise at qualifying high).
   - If the next candle fails to break the qualifying high, the setup lapses.

4. TARGET PROFIT (TP):
   - Fixed +40.0% Target Profit measured from the entry price:
       TP_Price = entry_price * (1.0 + 40.0 / 100.0) = entry_price * 1.40
   - Checked intrabar: triggers whenever High[t] >= TP_Price.
   - Gap-aware fill: exit_price = max(Open[t], TP_Price).

5. STOP LOSS (SL) - Weekly 30 EMA Breakdown:
   - In Weekly TF (W-FRI), track the 30-period EMA of weekly close.
   - When a weekly candle closes below the 30 EMA (Close_w < EMA30_w):
     The LOW of this weekly candle becomes the armed Stop Loss level (armed_sl_low).
   - When subsequent daily price breaks below this armed low (Low < armed_sl_low):
     Exit immediately! Exit price = min(Open, armed_sl_low) / armed_sl_low.
     Exit Reason = "Stop Loss (Weekly Close Below 30 EMA and Low Broken)".
   - Disarm condition: If price closes back above the 30 EMA on a weekly candle
     without breaking the armed low, the breakdown is disarmed (armed_sl_low = None).

6. OPTIONAL PRE-FILTERS:
   - Market Cap, ROE, PE, Debt/Equity, and Net Profitability gates (disabled by default = 0 / False).
"""

import os
import json
import numpy as np
import pandas as pd

# =========================================================================
# CONFIGURABLE STRATEGY PARAMETERS
# =========================================================================
TP_PCT = 300.0                     # Target Profit % (+40.0% from entry price)
WEEKLY_EMA_PERIOD = 30            # Weekly EMA period for Stop Loss (30 EMA)
DEFAULT_SL_PCT = 10.0             # Fallback Stop Loss % display indicator for generic UI consumers
MAX_BREAKOUT_WAIT_DAYS = 1        # Max days to wait for breakout of qualifying high (1 = immediate next candle)
MAX_HOLD_DAYS = 500               # Max holding days safety cap

# Fundamental Pre-Filters (0.0 / False to disable)
MIN_MARKET_CAP_CR = 0.0           # Minimum Market Cap in ₹ Crores (0 to disable)
MIN_ROE = 0.0                     # Minimum ROE % (0 to disable)
MAX_PE = 0.0                      # Maximum P/E (0 to disable)
MAX_DEBT_TO_EQUITY = 0.0          # Maximum Debt/Equity (0 to disable)
REQUIRE_PROFITABLE = False        # Strictly require positive Net Profit for recent quarters
PROFITABLE_QUARTERS = 2           # Number of recent quarters to check for profitability


# =========================================================================
# FUNDAMENTAL HELPERS
# =========================================================================
def _load_statement_data(symbol: str) -> dict:
    """Safely loads financial statements from sandbox globals, app module, or local json cache."""
    if not symbol:
        return {}
    try:
        if 'get_stock_statement' in globals() and callable(globals()['get_stock_statement']):
            res = globals()['get_stock_statement'](symbol, fetch_online=False)
            if res:
                return res
        try:
            from app import get_stock_statement
            res = get_stock_statement(symbol, fetch_online=False)
            if res:
                return res
        except Exception:
            pass
        clean_sym = str(symbol).upper().replace('.NS', '').strip()
        stmt_path = os.path.join('data', 'fundamentals', 'statements', f"{clean_sym}.json")
        if os.path.exists(stmt_path):
            with open(stmt_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def check_profitable(symbol: str, quarters: int = 2) -> bool:
    """Verifies that the stock's Net Profit is strictly positive (> 0) for recent quarters."""
    if not symbol or quarters <= 0:
        return False
    stmt = _load_statement_data(symbol)
    if not stmt:
        return False
    qpnl = stmt.get('quarterly_pnl', {})
    metrics = qpnl.get('metrics', {})
    ni_dict = (
        metrics.get('Net Income') or
        metrics.get('Net Income Common Stockholders') or
        metrics.get('Normalized Income') or
        metrics.get('Net Income Including Noncontrolling Interests') or
        metrics.get('Net Profit') or
        metrics.get('Profit After Tax')
    )
    if not ni_dict:
        return False

    dates = qpnl.get('dates', [])
    ni_vals = []
    for d in dates:
        v = ni_dict.get(d)
        if v is not None and not pd.isna(v):
            try:
                val = float(v)
                ni_vals.append(val)
                if len(ni_vals) == quarters:
                    break
            except (ValueError, TypeError):
                pass

    if len(ni_vals) < quarters:
        return False

    for v in ni_vals:
        if v <= 0:
            return False

    return True


# =========================================================================
# PIVOT CALCULATION HELPERS (Lookahead-Bias Free)
# =========================================================================
def compute_pivots(df: pd.DataFrame):
    """
    Computes Monthly R3 and Yearly R2 strictly from PRIOR completed periods:
      Yearly Pivots:
        Yearly_PP = (High_y + Low_y + Close_y) / 3.0
        Yearly_R2 = Yearly_PP + (High_y - Low_y)
      Monthly Pivots:
        Monthly_PP = (High_m + Low_m + Close_m) / 3.0
        Monthly_R3 = Monthly_PP + 2.0 * (High_m - Low_m)
    """
    if 'date' in df.columns:
        dt_series = pd.to_datetime(df['date'])
    elif isinstance(df.index, pd.DatetimeIndex):
        dt_series = pd.Series(df.index, index=df.index)
    else:
        dt_series = pd.to_datetime(pd.Series(df.index, index=df.index))

    year_period = dt_series.dt.to_period('Y')
    yearly_ohlc = pd.DataFrame({
        'high': df['high'].values, 'low': df['low'].values, 'close': df['close'].values
    }, index=df.index).groupby(year_period).agg(
        high=('high', 'max'), low=('low', 'min'), close=('close', 'last')
    )
    yearly_pp = (yearly_ohlc['high'] + yearly_ohlc['low'] + yearly_ohlc['close']) / 3.0
    yearly_r2 = yearly_pp + (yearly_ohlc['high'] - yearly_ohlc['low'])

    # Lag by 1 full completed year
    yearly_r2_shifted = yearly_r2.shift(1)
    yearly_pp_shifted = yearly_pp.shift(1)

    yearly_r2_arr = year_period.map(yearly_r2_shifted).to_numpy(dtype=float)
    yearly_pp_arr = year_period.map(yearly_pp_shifted).to_numpy(dtype=float)

    # Monthly Period: PP + 2*(High - Low)
    month_period = dt_series.dt.to_period('M')
    monthly_ohlc = pd.DataFrame({
        'high': df['high'].values, 'low': df['low'].values, 'close': df['close'].values
    }, index=df.index).groupby(month_period).agg(
        high=('high', 'max'), low=('low', 'min'), close=('close', 'last')
    )
    monthly_pp = (monthly_ohlc['high'] + monthly_ohlc['low'] + monthly_ohlc['close']) / 3.0
    monthly_r3 = monthly_pp + 2.0 * (monthly_ohlc['high'] - monthly_ohlc['low'])

    # Lag by 1 full completed month
    monthly_r3_shifted = monthly_r3.shift(1)
    monthly_pp_shifted = monthly_pp.shift(1)

    monthly_r3_arr = month_period.map(monthly_r3_shifted).to_numpy(dtype=float)
    monthly_pp_arr = month_period.map(monthly_pp_shifted).to_numpy(dtype=float)

    return yearly_r2_arr, monthly_r3_arr, yearly_pp_arr, monthly_pp_arr


def _compute_weekly_30_ema(df: pd.DataFrame):
    """
    Resamples daily data to weekly candles (W-FRI) and computes 30-period EMA of close.
    Returns weekly dataframe and arrays.
    """
    temp_df = df.copy()
    if 'date' in temp_df.columns:
        temp_df.index = pd.to_datetime(temp_df['date'])
    elif not isinstance(temp_df.index, pd.DatetimeIndex):
        temp_df.index = pd.to_datetime(temp_df.index)

    w_df = temp_df.resample('W-FRI').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna(subset=['close'])

    w_df['w_ema30'] = w_df['close'].ewm(span=WEEKLY_EMA_PERIOD, adjust=False).mean()
    return w_df


# =========================================================================
# TRADE SIMULATION ENGINE
# =========================================================================
def simulate_trades(df: pd.DataFrame):
    """
    Simulates trades with:
    - Qualification: Daily Close > Monthly R3 (fresh cross) AND Daily Close > Yearly R2.
    - Entry: Next day breaks qualifying high (Buy-stop at qualifying high).
    - TP: 40% (+40.0% gain).
    - SL: Weekly candle closes below 30 EMA, low of that weekly candle is the SL.
    """
    n = len(df)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)
    dates = df['date'].astype(str).to_numpy() if 'date' in df.columns else df.index.astype(str).to_numpy()
    d_indices = df.index if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(dates)

    yearly_r2, monthly_r3, yearly_pp, monthly_pp = compute_pivots(df)
    w_df = _compute_weekly_30_ema(df)

    w_close = w_df['close'].to_numpy(dtype=float)
    w_low = w_df['low'].to_numpy(dtype=float)
    w_ema30 = w_df['w_ema30'].to_numpy(dtype=float)
    w_indices = w_df.index

    long_entry = np.zeros(n, dtype=bool)
    signal = np.zeros(n, dtype=bool)
    tp_pct_arr = np.full(n, np.nan)
    sl_pct_arr = np.full(n, DEFAULT_SL_PCT)
    active_sl_arr = np.full(n, np.nan)
    active_tp_arr = np.full(n, np.nan)
    trades = []

    state = "IDLE"  # "IDLE", "AWAITING_BREAKOUT", "IN_TRADE"
    qualifying_high = None
    qualifying_idx = None

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

        if state == "IDLE":
            if np.isnan(monthly_r3[i]) or np.isnan(yearly_r2[i]):
                i += 1
                continue

            # 1. Setup Qualification:
            # - Daily candle closes above Monthly R3
            # - Fresh cross: previous candle was at or below Monthly R3
            # - When this candle has closed above Monthly R3, it should be above Yearly R2
            fresh_mr3_breakout = (close[i] > monthly_r3[i]) and (
                np.isnan(monthly_r3[i - 1]) or close[i - 1] <= monthly_r3[i - 1]
            )
            above_yearly_r2 = close[i] > yearly_r2[i]

            if fresh_mr3_breakout and above_yearly_r2:
                signal[i] = True
                qualifying_high = high[i]
                qualifying_idx = i
                state = "AWAITING_BREAKOUT"

            i += 1
            continue

        elif state == "AWAITING_BREAKOUT":
            # Buy-stop order placed at the qualifying candle's HIGH
            days_waiting = i - qualifying_idx

            if high[i] > qualifying_high:
                # ENTRY TRIGGERED!
                trade_entry_idx = i
                entry_price = qualifying_high if open_[i] <= qualifying_high else open_[i]
                tp_price = entry_price * (1.0 + TP_PCT / 100.0)
                state = "IN_TRADE"
                armed_sl_low = None
                last_checked_w_idx = -1

                long_entry[i] = True
                tp_pct_arr[i] = TP_PCT
                active_tp_arr[i] = tp_price
                sl_pct_arr[i] = DEFAULT_SL_PCT

                mae = (entry_price - low[i]) / entry_price * 100.0
                mfe = (high[i] - entry_price) / entry_price * 100.0

                # Check 1: Same bar Intrabar TP
                if high[i] >= tp_price:
                    exit_p = tp_price if open_[i] <= tp_price else open_[i]
                    trades.append({
                        "entry_date": dates[i],
                        "entry_price": round(float(entry_price), 2),
                        "exit_date": dates[i],
                        "exit_price": round(float(exit_p), 2),
                        "exit_reason": f"Target Profit ({int(TP_PCT)}% Same Bar)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
                    })
                    state = "IDLE"
                    i += 1
                    continue

                i += 1
                continue
            else:
                # Next candle did not break qualifying high
                if days_waiting >= MAX_BREAKOUT_WAIT_DAYS:
                    state = "IDLE"
                    # Re-evaluate candle i for potential fresh breakout
                    continue
                else:
                    i += 1
                    continue

        elif state == "IN_TRADE":
            mae = max(mae, (entry_price - low[i]) / entry_price * 100.0)
            mfe = max(mfe, (high[i] - entry_price) / entry_price * 100.0)

            # Synchronize weekly 30 EMA breakdown up to prior completed week
            w_past = np.where(w_indices < cur_date.floor('D'))[0]
            if len(w_past) > 0:
                cur_w_idx = w_past[-1]
                if cur_w_idx > last_checked_w_idx and cur_w_idx >= 0:
                    if w_close[cur_w_idx] < w_ema30[cur_w_idx]:
                        # Weekly candle closed below 30 EMA -> arm that weekly candle's LOW
                        armed_sl_low = w_low[cur_w_idx] if armed_sl_low is None else min(armed_sl_low, w_low[cur_w_idx])
                    else:
                        # Closed back above 30 EMA -> breakdown disarmed
                        armed_sl_low = None
                    last_checked_w_idx = cur_w_idx

            active_tp_arr[i] = tp_price
            active_sl_arr[i] = armed_sl_low if armed_sl_low is not None else np.nan

            bars_in_trade = i - trade_entry_idx
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

            # 1. Target Profit check: +40%
            if high[i] >= tp_price:
                exit_p = tp_price if open_[i] <= tp_price else open_[i]
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates[i],
                    "exit_price": round(float(exit_p), 2),
                    "exit_reason": f"Target Profit ({int(TP_PCT)}%)",
                    "mae_pct": round(float(mae), 2),
                    "mfe_pct": round(float(mfe), 2),
                    "is_open": False,
                })
                state = "IDLE"
                armed_sl_low = None
                i += 1
                continue

            # 2. Stop Loss check: Weekly close below 30 EMA and low of that candle broken
            if armed_sl_low is not None and low[i] < armed_sl_low:
                exit_p = armed_sl_low if open_[i] >= armed_sl_low else open_[i]
                trades.append({
                    "entry_date": dates[trade_entry_idx],
                    "entry_price": round(float(entry_price), 2),
                    "exit_date": dates[i],
                    "exit_price": round(float(exit_p), 2),
                    "exit_reason": "Stop Loss (Weekly Close Below 30 EMA and Low Broken)",
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

    # Final open trade handling
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

    extra_cols = {
        'Monthly_R3': monthly_r3,
        'Yearly_R2': yearly_r2,
        'Yearly_PP': yearly_pp,
        'Monthly_PP': monthly_pp,
        'Active_TP': active_tp_arr,
        'Active_SL': active_sl_arr,
    }

    return trades, long_entry, signal, tp_pct_arr, sl_pct_arr, extra_cols


# =========================================================================
# MAIN BACKTEST / SCREEN ENTRY POINT
# =========================================================================
def backtest(df: pd.DataFrame) -> dict:
    df = df.copy()

    # Column name standardization
    clean_cols = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow in ['open', 'high', 'low', 'close', 'volume', 'date', 'symbol', 'market_cap_cr', 'roe', 'pe', 'debt_to_equity'] and clow not in clean_cols.values():
            clean_cols[c] = clow
    df_clean = df[list(clean_cols.keys())].rename(columns=clean_cols)

    if 'date' in df_clean.columns and not isinstance(df_clean.index, pd.DatetimeIndex):
        df_clean.index = pd.to_datetime(df_clean['date'])
    elif not isinstance(df_clean.index, pd.DatetimeIndex):
        df_clean.index = pd.to_datetime(df_clean.index)

    df_clean = df_clean.sort_index()

    for col in ('open', 'high', 'low', 'close'):
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    df_clean = df_clean.dropna(subset=['open', 'high', 'low', 'close'])

    if 'volume' not in df_clean.columns:
        df_clean['volume'] = 100_000.0

    if 'date' not in df_clean.columns:
        df_clean['date'] = df_clean.index.strftime('%Y-%m-%d')
    df_clean['Date'] = df_clean['date']

    empty_res = {
        "trades": [],
        "long_entry": pd.Series(False, index=df_clean.index),
        "entries": pd.Series(False, index=df_clean.index),
        "signal": pd.Series(False, index=df_clean.index),
        "tp_pct": pd.Series(TP_PCT, index=df_clean.index),
        "sl_pct": pd.Series(DEFAULT_SL_PCT, index=df_clean.index),
        "df": df_clean
    }

    n = len(df_clean)
    if n < 40:  # Needs at least 1-2 months to compute prior monthly R3
        return empty_res

    # -------------------------------------------------------------------------
    # FUNDAMENTAL PRE-FILTER GATES (Optional)
    # -------------------------------------------------------------------------
    symbol = None
    for c in ['symbol', 'Symbol', 'SYMBOL', 'ticker', 'Ticker']:
        if c in df.columns:
            s_vals = df[c].dropna()
            if not s_vals.empty:
                symbol = str(s_vals.iloc[-1]).upper().replace('.NS', '').strip()
                break
    if not symbol and hasattr(df, 'attrs') and 'symbol' in df.attrs:
        symbol = str(df.attrs['symbol']).upper().replace('.NS', '').strip()
    if not symbol and hasattr(df, 'name') and df.name:
        symbol = str(df.name).upper().replace('.NS', '').strip()

    def _last(col):
        for c in [col, col.lower(), col.upper()]:
            if c in df.columns and pd.notna(df[c].iloc[-1]):
                try:
                    return float(df[c].iloc[-1])
                except (ValueError, TypeError):
                    pass
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

    if REQUIRE_PROFITABLE and symbol:
        if not check_profitable(symbol, quarters=PROFITABLE_QUARTERS):
            return empty_res

    # -------------------------------------------------------------------------
    # RUN SIMULATION
    # -------------------------------------------------------------------------
    trades, long_entry_arr, signal_arr, tp_pct_arr, sl_pct_arr, extra_cols = simulate_trades(df_clean)

    out_df = df_clean.copy()
    for k, v in extra_cols.items():
        out_df[k] = v
    out_df['Signal'] = signal_arr
    out_df['Long_Entry'] = long_entry_arr

    return {
        "trades": trades,
        "long_entry": pd.Series(long_entry_arr, index=df_clean.index),
        "entries": pd.Series(long_entry_arr, index=df_clean.index),
        "signal": pd.Series(signal_arr, index=df_clean.index),
        "tp_pct": pd.Series(tp_pct_arr, index=df_clean.index).fillna(TP_PCT),
        "sl_pct": pd.Series(sl_pct_arr, index=df_clean.index).fillna(DEFAULT_SL_PCT),
        "df": out_df
    }


screen = backtest
"""
Weekly Yearly-R1 Trigger (RSI > 75) + Daily Monthly-R1 Breakout Strategy (Daily Swing)
=======================================================================================
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).
Designed for Daily OHLCV data -- weekly and yearly pivots + RSI are computed internally.

STRATEGY RULES:
1. BUY TRIGGER (Weekly Timeframe):
   - In Weekly TF, the candle must close above the Yearly R1 resistance level:
       PP_year = (High_year + Low_year + Close_year) / 3
       R1_year = 2 * PP_year - Low_year
     computed from the PRIOR completed calendar year's OHLC and held constant.
   - RSI Filter: The weekly candle must be ABOVE RSI 75 (Weekly RSI > 75).
   - Sequential Carry-Forward Rule: If the initial candle closing above Yearly R1
     does not have RSI > 75, any subsequent weekly candle that reaches RSI > 75
     arms the trigger, provided the candle is STILL closing above Yearly R1.
   - If a weekly candle closes below Yearly R1, the armed trigger resets to False.

2. BUY SIGNAL (Daily Timeframe):
   - As soon as the weekly trigger is armed, in Daily TF, the daily candle must
     close above THAT MONTH's Monthly R1:
       PP_month = (High_month + Low_month + Close_month) / 3
       R1_month = 2 * PP_month - Low_month
     computed from the PRIOR completed calendar month's OHLC and held constant.
   - When a daily candle closes above Monthly R1 (Close > Monthly R1):
     BUY at the HIGH of this daily candle (entry_price = signal_candle.High).

3. TARGET PROFIT (TP):
   - Fixed 50.0% swing profit target measured from the entry price:
       TP_Price = Entry_Price * (1.0 + 0.50)

4. STOP LOSS (SL):
   - The Daily candle which we bought, THIS MONTH'S PIVOT POINT (Monthly PP):
       SL_Price = Monthly_PP of the month in which the buy candle occurred.
   - Fixed at entry: once set, this SL price remains constant throughout the trade.
   - Validated intrabar (low <= SL_Price) with gap-aware execution, or
     configurable to close-confirmed (close < SL_Price).

5. LIQUIDITY & MARKET CAP GATE:
   - Optional Market Cap filter: MIN_MARKET_CAP_CR (default Rs 2,000 Cr; 0 to disable).
"""

import numpy as np
import pandas as pd

# =========================================================================
# CONFIGURABLE PARAMETERS
# =========================================================================
MIN_MARKET_CAP_CR = 2000.0        # Minimum Market Cap in ₹ Crores (0 to disable)
WEEKLY_RSI_PERIOD = 14            # Period for Weekly RSI calculation
MIN_WEEKLY_RSI = 75.0             # Weekly RSI threshold (candle must be above 75)
TP_PCT = 50.0                     # Target Profit % (50.0%)
DEFAULT_SL_PCT = 10.0             # Fallback Stop Loss % for generic scalar consumers
SL_MODE = "intrabar"              # "intrabar" (low <= SL) or "close" (close < SL)


# =========================================================================
# TECHNICAL INDICATOR HELPERS
# =========================================================================
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Standard Wilder's Relative Strength Index (RSI).
    Matches TradingView and Zerodha Kite smoothing.
    """
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


# =========================================================================
# PIVOT CALCULATION HELPERS
# =========================================================================
def _compute_yearly_pivots(df: pd.DataFrame, year_period: pd.PeriodIndex):
    """
    Computes Yearly Pivot Point (PP) and Yearly R1 from the PRIOR completed calendar year's OHLC,
    held constant across all days of the current calendar year.
    """
    yearly_ohlc = pd.DataFrame({
        'high': df['high'], 'low': df['low'], 'close': df['close']
    }, index=df.index).groupby(year_period).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    
    yearly_pp = (yearly_ohlc['high'] + yearly_ohlc['low'] + yearly_ohlc['close']) / 3.0
    yearly_r1 = 2.0 * yearly_pp - yearly_ohlc['low']
    
    yr1_shifted = yearly_r1.shift(1)
    ypp_shifted = yearly_pp.shift(1)
    
    yearly_r1_for_row = year_period.map(yr1_shifted).to_numpy(dtype=float)
    yearly_pp_for_row = year_period.map(ypp_shifted).to_numpy(dtype=float)
    return yearly_pp_for_row, yearly_r1_for_row, yr1_shifted


def _compute_monthly_pivots(df: pd.DataFrame, month_period: pd.PeriodIndex):
    """
    Computes Monthly Pivot Point (PP) and Monthly R1 from the PRIOR completed calendar month's OHLC,
    held constant across all days of the current calendar month.
    """
    monthly_ohlc = pd.DataFrame({
        'high': df['high'], 'low': df['low'], 'close': df['close']
    }, index=df.index).groupby(month_period).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    
    monthly_pp = (monthly_ohlc['high'] + monthly_ohlc['low'] + monthly_ohlc['close']) / 3.0
    monthly_r1 = 2.0 * monthly_pp - monthly_ohlc['low']
    
    mpp_shifted = monthly_pp.shift(1)
    mr1_shifted = monthly_r1.shift(1)
    
    monthly_pp_for_row = month_period.map(mpp_shifted).to_numpy(dtype=float)
    monthly_r1_for_row = month_period.map(mr1_shifted).to_numpy(dtype=float)
    return monthly_pp_for_row, monthly_r1_for_row


def _compute_weekly_trigger(df: pd.DataFrame, yr1_shifted_by_year: pd.Series):
    """
    Resamples daily data to weekly (W-FRI) candles, computes Weekly RSI, and evaluates:
    1. Weekly candle Close > Yearly R1.
    2. Weekly RSI > MIN_WEEKLY_RSI (75).
    3. If initial candle above R1 has RSI <= 75, any subsequent weekly candle above R1
       that reaches RSI > 75 arms the trigger.
    4. If weekly candle closes below Yearly R1, the armed trigger resets to False.
    """
    weekly_ohlc = df.resample('W-FRI').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last')
    ).dropna(subset=['close'])
    
    weekly_ohlc['rsi'] = compute_rsi(weekly_ohlc['close'], WEEKLY_RSI_PERIOD)
    
    weekly_year = weekly_ohlc.index.to_period('Y')
    weekly_yr1 = weekly_year.map(yr1_shifted_by_year)
    weekly_above_r1 = (weekly_ohlc['close'] > weekly_yr1)
    weekly_rsi_gt_75 = (weekly_ohlc['rsi'] > MIN_WEEKLY_RSI)
    
    # State tracking: arms on first week that achieves RSI > 75 while above Yearly R1,
    # and stays armed as long as subsequent weekly closes remain above Yearly R1.
    n_w = len(weekly_ohlc)
    weekly_armed = np.zeros(n_w, dtype=bool)
    cycle_armed = False
    
    for i in range(n_w):
        if weekly_above_r1.iloc[i]:
            if weekly_rsi_gt_75.iloc[i]:
                cycle_armed = True
            weekly_armed[i] = cycle_armed
        else:
            cycle_armed = False
            weekly_armed[i] = False
            
    weekly_status_df = pd.DataFrame({
        'w_close': weekly_ohlc['close'],
        'w_rsi': weekly_ohlc['rsi'],
        'w_yr1': weekly_yr1,
        'w_above_r1': weekly_above_r1,
        'w_rsi_gt_75': weekly_rsi_gt_75,
        'w_armed': weekly_armed
    }, index=weekly_ohlc.index)
    
    daily_dates = df.index
    w_indices = weekly_status_df.index
    
    daily_w_armed = np.zeros(len(df), dtype=bool)
    daily_w_above_r1 = np.zeros(len(df), dtype=bool)
    daily_w_rsi_gt_75 = np.zeros(len(df), dtype=bool)
    daily_w_close = np.full(len(df), np.nan)
    daily_w_rsi = np.full(len(df), np.nan)
    
    # Map each daily date to the most recently completed weekly bar without lookahead bias
    for i, d in enumerate(daily_dates):
        past_w = w_indices[w_indices <= d]
        if len(past_w) > 0:
            last_w = past_w[-1]
            daily_w_armed[i] = bool(weekly_status_df.loc[last_w, 'w_armed'])
            daily_w_above_r1[i] = bool(weekly_status_df.loc[last_w, 'w_above_r1'])
            daily_w_rsi_gt_75[i] = bool(weekly_status_df.loc[last_w, 'w_rsi_gt_75'])
            daily_w_close[i] = float(weekly_status_df.loc[last_w, 'w_close'])
            daily_w_rsi[i] = float(weekly_status_df.loc[last_w, 'w_rsi'])
            
    return (daily_w_armed, daily_w_above_r1, daily_w_rsi_gt_75,
            daily_w_close, daily_w_rsi)


# =========================================================================
# SIGNAL GENERATION LOGIC
# =========================================================================
def _compute_signals(df: pd.DataFrame):
    """
    Generates Buy Signals where:
    1. Weekly candle closed above Yearly R1 with RSI > 75 (Weekly Trigger armed).
    2. Daily candle closes above Monthly R1 (Daily Breakout confirmed).
    3. Buy at High of this daily candle.
    4. SL = Monthly Pivot Point of this entry month.
    """
    n = len(df)
    year_period = df.index.to_period('Y')
    month_period = df.index.to_period('M')
    
    yearly_pp, yearly_r1, yr1_shifted = _compute_yearly_pivots(df, year_period)
    monthly_pp, monthly_r1 = _compute_monthly_pivots(df, month_period)
    (weekly_armed, weekly_above_r1, weekly_rsi_gt_75,
     weekly_close, weekly_rsi) = _compute_weekly_trigger(df, yr1_shifted)
    
    close = df['close'].to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    
    daily_above_mr1 = ~np.isnan(monthly_r1) & (close > monthly_r1)
    
    entries = np.zeros(n, dtype=bool)
    entry_price_arr = np.full(n, np.nan)
    sl_price_arr = np.full(n, np.nan)
    tp_price_arr = np.full(n, np.nan)
    stage_arr = np.full(n, "IDLE", dtype=object)
    
    for i in range(1, n):
        if np.isnan(yearly_r1[i]) or np.isnan(monthly_r1[i]) or np.isnan(monthly_pp[i]):
            stage_arr[i] = "WARMUP"
            continue
            
        is_weekly_armed = weekly_armed[i]
        is_daily_close_above = daily_above_mr1[i]
        
        # Fresh daily breakout: closes above Monthly R1 when yesterday wasn't or trigger was not armed
        is_fresh_daily_breakout = is_daily_close_above and (not daily_above_mr1[i - 1] or not weekly_armed[i - 1])
        
        if is_weekly_armed and is_daily_close_above:
            if is_fresh_daily_breakout:
                entries[i] = True
                entry_price_arr[i] = high[i]          # Buy at high of this candle
                sl_price_arr[i] = monthly_pp[i]       # This month's Pivot point
                tp_price_arr[i] = high[i] * (1.0 + TP_PCT / 100.0)
                stage_arr[i] = "BUY_SIGNAL"
            else:
                stage_arr[i] = "ABOVE_MR1_RUNNING"
        elif is_weekly_armed:
            stage_arr[i] = "WEEKLY_ARMED_WAITING_DAILY"
        elif weekly_above_r1[i]:
            stage_arr[i] = "ABOVE_YR1_WAITING_RSI"
        else:
            stage_arr[i] = "IDLE"
            
    return (entries, entry_price_arr, sl_price_arr, tp_price_arr, stage_arr,
            yearly_r1, monthly_r1, monthly_pp, weekly_armed, weekly_above_r1,
            weekly_rsi_gt_75, weekly_close, weekly_rsi)


# =========================================================================
# WALK-FORWARD TRADE SIMULATION
# =========================================================================
def _simulate_one_trade(low, high, close, opn, entry_idx, entry_price, tp_price, sl_price, dates):
    """
    Simulates a single trade lifecycle walking forward from entry_idx + 1:
    - Checks 50% Target Profit (TP) hit.
    - Checks Stop Loss (Monthly Pivot Point of entry candle's month).
    - Returns: exit_idx, exit_price, exit_reason, mae_pct, mfe_pct.
    """
    n = len(close)
    min_low = low[entry_idx]
    max_high = high[entry_idx]
    
    for i in range(entry_idx + 1, n):
        min_low = min(min_low, low[i])
        max_high = max(max_high, high[i])
        
        hit_tp = high[i] >= tp_price
        hit_sl = (low[i] <= sl_price) if SL_MODE == "intrabar" else (close[i] < sl_price)
        
        if hit_tp and hit_sl:
            if opn[i] >= entry_price:
                exit_price = max(tp_price, opn[i])
                reason = "Target Profit (TP 50%)"
            else:
                exit_price = min(sl_price, opn[i])
                reason = "Stop Loss (Monthly Pivot)"
            mae_pct = (min_low - entry_price) / entry_price * 100.0
            mfe_pct = (max_high - entry_price) / entry_price * 100.0
            return i, exit_price, reason, mae_pct, mfe_pct
            
        if hit_tp:
            exit_price = opn[i] if opn[i] >= tp_price else tp_price
            mae_pct = (min_low - entry_price) / entry_price * 100.0
            mfe_pct = (max_high - entry_price) / entry_price * 100.0
            return i, exit_price, "Target Profit (TP 50%)", mae_pct, mfe_pct
            
        if hit_sl:
            if SL_MODE == "intrabar":
                exit_price = min(sl_price, opn[i]) if opn[i] < sl_price else sl_price
            else:
                exit_price = close[i]
            mae_pct = (min_low - entry_price) / entry_price * 100.0
            mfe_pct = (max_high - entry_price) / entry_price * 100.0
            return i, exit_price, "Stop Loss (Monthly Pivot)", mae_pct, mfe_pct
            
    # Reached end of available data with position still open
    mae_pct = (min_low - entry_price) / entry_price * 100.0
    mfe_pct = (max_high - entry_price) / entry_price * 100.0
    return n - 1, close[-1], "End of Data", mae_pct, mfe_pct


# =========================================================================
# STANDALONE SIMULATION FUNCTION
# =========================================================================
def simulate_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a pandas DataFrame of all simulated trades for detailed inspection."""
    res = backtest(df)
    trades = res.get("trades", [])
    if not trades:
        return pd.DataFrame(columns=[
            "Entry Date", "Entry Price", "SL Price", "TP Price",
            "Exit Date", "Exit Price", "Exit Reason", "MAE (%)", "MFE (%)", "PnL (%)"
        ])
    
    rows = []
    for t in trades:
        rows.append({
            "Entry Date": t["entry_date"],
            "Entry Price": t["entry_price"],
            "SL Price": t["sl_price"],
            "TP Price": t.get("tp_price", round(t["entry_price"] * 1.50, 2)),
            "Exit Date": t["exit_date"],
            "Exit Price": t["exit_price"],
            "Exit Reason": t["exit_reason"],
            "MAE (%)": t["mae_pct"],
            "MFE (%)": t["mfe_pct"],
            "PnL (%)": round((t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100.0, 2),
        })
    return pd.DataFrame(rows)


# =========================================================================
# MAIN BACKTEST / SCREEN ENTRY POINT
# =========================================================================
def backtest(df: pd.DataFrame) -> dict:
    df = df.copy()
    
    # -------------------------------------------------------------------------
    # 1. Fundamental Pre-Filter Gate (Market Cap)
    # -------------------------------------------------------------------------
    if 'Market_Cap_Cr' in df.columns:
        mcap = df['Market_Cap_Cr'].iloc[-1]
        if mcap is not None and not np.isnan(mcap) and MIN_MARKET_CAP_CR > 0 and mcap < MIN_MARKET_CAP_CR:
            return {
                "trades": [],
                "long_entry": pd.Series(False, index=df.index, name="long_entry"),
                "entries": pd.Series(False, index=df.index, name="entries"),
                "signal": pd.Series(False, index=df.index, name="signal"),
                "tp_pct": pd.Series(np.nan, index=df.index, name="tp_pct"),
                "sl_pct": pd.Series(np.nan, index=df.index, name="sl_pct"),
                "df": df
            }
            
    # -------------------------------------------------------------------------
    # 2. Column Standardization & Datetime Indexing
    # -------------------------------------------------------------------------
    clean_cols = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow in ['open', 'high', 'low', 'close', 'volume', 'prev_close', 'date', 'market_cap_cr', 'symbol'] and clow not in clean_cols.values():
            clean_cols[c] = clow
    df = df[list(clean_cols.keys())].rename(columns=clean_cols)
    
    if 'date' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df['date'])
    df = df.sort_index()
    
    for col in ('open', 'high', 'low', 'close'):
        if col not in df.columns:
            raise ValueError(f"df is missing required column '{col}'")
            
    if 'volume' not in df.columns:
        df['volume'] = 100_000
    if 'prev_close' not in df.columns:
        df['prev_close'] = df['close'].shift(1).fillna(df['open'])
        
    n = len(df)
    date_strs = df['date'].astype(str).values if 'date' in df.columns else df.index.astype(str).values
    
    # -------------------------------------------------------------------------
    # 3. Compute Signals & Pivot Levels
    # -------------------------------------------------------------------------
    (raw_entries, entry_price_arr, sl_price_arr, tp_price_arr, stage_arr,
     yearly_r1, monthly_r1, monthly_pp, weekly_armed, weekly_above_r1,
     weekly_rsi_gt_75, weekly_close, weekly_rsi) = _compute_signals(df)
     
    close = df['close'].to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    opn = df['open'].to_numpy(dtype=float)
    
    # -------------------------------------------------------------------------
    # 4. Simulate Trades (Non-overlapping sequential trades)
    # -------------------------------------------------------------------------
    trades = []
    executed_entries = np.zeros(n, dtype=bool)
    sl_pct_arr = np.full(n, DEFAULT_SL_PCT)
    tp_pct_arr = np.full(n, TP_PCT)
    
    i = 0
    while i < n:
        if raw_entries[i] and not np.isnan(entry_price_arr[i]) and not np.isnan(sl_price_arr[i]):
            ep = entry_price_arr[i]
            sp = sl_price_arr[i]
            tp = tp_price_arr[i]
            
            executed_entries[i] = True
            if ep > 0:
                sl_pct_arr[i] = round(abs(ep - sp) / ep * 100.0, 2)
                
            ex_idx, ex_p, reason, mae_pct, mfe_pct = _simulate_one_trade(
                low, high, close, opn, i, ep, tp, sp, date_strs
            )
            
            trades.append({
                "entry_date": str(date_strs[i])[:10],
                "entry_price": round(float(ep), 2),
                "sl_price": round(float(sp), 2),
                "tp_price": round(float(tp), 2),
                "exit_date": str(date_strs[ex_idx])[:10],
                "exit_price": round(float(ex_p), 2),
                "exit_reason": reason,
                "mae_pct": round(float(mae_pct), 2),
                "mfe_pct": round(float(mfe_pct), 2),
                "is_open": (reason == "End of Data")
            })
            i = ex_idx + 1
        else:
            i += 1
            
    # -------------------------------------------------------------------------
    # 5. Output DataFrame with Indicators for Charts & Tables
    # -------------------------------------------------------------------------
    out_df = df.copy()
    for col in ['open', 'high', 'low', 'close', 'volume', 'prev_close']:
        if col in out_df.columns and col.capitalize() not in out_df.columns:
            out_df[col.capitalize()] = out_df[col]
            
    out_df['Yearly_R1'] = yearly_r1
    out_df['Monthly_R1'] = monthly_r1
    out_df['Monthly_Pivot'] = monthly_pp
    out_df['Weekly_Close'] = weekly_close
    out_df['Weekly_RSI'] = weekly_rsi
    out_df['Weekly_Above_Yearly_R1'] = weekly_above_r1
    out_df['Weekly_RSI_Above_75'] = weekly_rsi_gt_75
    out_df['Weekly_Trigger_Armed'] = weekly_armed
    out_df['Daily_Close_Above_Monthly_R1'] = (out_df['close'] > monthly_r1)
    out_df['Setup_Stage'] = stage_arr
    out_df['entry_price'] = entry_price_arr
    out_df['sl_price'] = sl_price_arr
    out_df['tp_price'] = tp_price_arr
    out_df['Date'] = [str(d)[:10] for d in date_strs]
    
    return {
        "trades": trades,
        "long_entry": pd.Series(executed_entries, index=df.index, name="long_entry"),
        "entries": pd.Series(executed_entries, index=df.index, name="entries"),
        "signal": pd.Series(raw_entries, index=df.index, name="signal"),
        "tp_pct": pd.Series(tp_pct_arr, index=df.index, name="tp_pct"),
        "sl_pct": pd.Series(sl_pct_arr, index=df.index, name="sl_pct"),
        "df": out_df
    }

# Universal screener compatibility alias
screen = backtest

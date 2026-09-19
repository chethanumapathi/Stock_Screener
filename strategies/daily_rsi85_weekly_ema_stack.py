"""
Daily RSI 85 + Weekly 10/30/40 EMA Stack Strategy (Swing Trading)
==================================================================
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).
Accepts Daily OHLCV data -- Weekly EMAs, Yearly R1, and breakdown exits are evaluated internally.

STRATEGY RULES:

1. FUNDAMENTAL PRE-FILTER GATE:
   - QoQ Net Profit Growth Gate:
     * Strictly requires QoQ Net Profit to be profitable (> 0) across all checked quarters.
     * Net Profit must have strictly increased consecutively quarter-over-quarter for the last 2 quarters (Q0 > Q1 > Q2).
     * Any stock failing profitability or failing to increase for the last 2 quarters is rejected immediately.
   - Configurable pre-filters (Market Cap, ROE, PE, Debt/Equity) - disabled by default (0).

2. BUY SIGNAL / TRIGGER:
   - Daily Timeframe (Daily TF):
     The daily candle's 14-period RSI crosses strictly above 85:
       RSI_daily[t] > 85.0 and RSI_daily[t-1] <= 85.0
   - Weekly Timeframe (Weekly TF) Alignment:
     At the same time, in the weekly timeframe (W-FRI), the 10 EMA, 30 EMA,
     and 40 EMA of weekly close must be strictly arranged in bullish stacked order:
       1st: 10 EMA
       2nd: 30 EMA
       3rd: 40 EMA
       i.e. Weekly EMA_10 > Weekly EMA_30 > Weekly EMA_40
     (Mapped lookahead-free to daily candles using the prior completed weekly candle).

3. YEARLY R1 CHECK & ENTRY:
   - Yearly Pivot & R1 are computed from the PRIOR completed calendar year's OHLC:
       PP_year = (High_year + Low_year + Close_year) / 3
       R1_year = 2 * PP_year - Low_year
     and held constant across all daily candles of the current calendar year.
   - Case A (Already Above Yearly R1):
     If on the signal candle price is already above Yearly R1 (Close > Yearly R1):
       We BUY immediately at the HIGH of this qualifying candle (entry_price = High).
   - Case B (Below or At Yearly R1 -> Armed Buy Trigger):
     If price is NOT above Yearly R1 (Close <= Yearly R1), this becomes an ARMED BUY TRIGGER.
     We wait for a subsequent daily candle to CLOSE above the Yearly R1 (Close > Yearly R1).
     When a daily candle closes above Yearly R1, we BUY at the HIGH of this candle (entry_price = High).

4. TARGET PROFIT (TP):
   - Criteria 1: Fixed +100.0% Target Profit (2x the entry price):
       TP_Price = Entry_Price * (1.0 + 1.00) = Entry_Price * 2.0
   - Checked intrabar on daily bars whenever High >= TP_Price (gap-aware execution).

5. STOP LOSS / TRAILING EXIT:
   - Criteria 2: Weekly 30 EMA Breakdown Exit:
     When a weekly candle closes below the weekly 30-period EMA (Close_w < EMA30_w),
     its Low (Low_w) becomes the armed reference low.
     If the low of this candle gets broken by a subsequent candle (Low < armed_low),
     exit immediately at armed_low (or open if gapped down)!
     Exit reason = "Exit (Close Below 30 EMA and Low Broken)".
     (If price closes back above 30 EMA before the low is broken, the breakdown is disarmed).
"""

import os
import json
import numpy as np
import pandas as pd

# =========================================================================
# CONFIGURABLE PARAMETERS
# =========================================================================
MIN_MARKET_CAP_CR = 0.0          # Minimum Market Cap in ₹ Crores (0 to disable)
MIN_ROE = 0.0                    # Minimum ROE % (0 to disable)
MAX_PE = 0.0                     # Maximum P/E (0 to disable)
MAX_DEBT_TO_EQUITY = 0.0         # Maximum Debt-to-Equity (0 to disable)

REQUIRE_QOQ_PROFIT_GROWTH = True      # Strictly require QoQ Net Profit to be profitable (> 0) and increasing
QOQ_PROFIT_GROWTH_QUARTERS = 2        # Number of consecutive quarters Net Profit must have increased (last 2 qtrs)

DAILY_RSI_PERIOD = 14            # Period for Daily RSI calculation
DAILY_RSI_THRESHOLD = 85.0       # Daily RSI cross-above threshold

WEEKLY_EMA_FAST = 10             # Weekly 1st EMA
WEEKLY_EMA_MID = 30              # Weekly 2nd EMA
WEEKLY_EMA_SLOW = 40             # Weekly 3rd EMA

TP_PCT = 100.0                   # Fixed +100.0% Target Profit (2x entry price)
DEFAULT_SL_PCT = 10.0            # Fallback SL % for scalar consumers
MAX_HOLD_DAYS = 500              # Maximum trading days to hold a trade
NEXT_BAR_BREAKOUT = False        # If True, waits for next daily candle to break signal candle High
REQUIRE_WEEKLY_STACK_ON_R1_ENTRY = False # If True, requires weekly EMAs to still be stacked when closing above R1
MAX_R1_TRIGGER_WAIT_DAYS = 0     # Max days to wait for R1 close after trigger (0 = wait indefinitely until bought)


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


def check_qoq_profit_increasing(symbol: str, quarters: int = 2) -> bool:
    """
    Strictly verifies whether a stock's Net Profit / Income is:
    1. Strictly profitable (> 0) for each of the last (quarters + 1) quarters.
    2. Strictly increasing quarter-over-quarter (QoQ) consecutively for `quarters` periods:
       Q_0 > Q_1 > Q_2 (for quarters=2).
    Returns False if quarterly data is missing, unprofitable, or failed to increase.
    """
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
        metrics.get('Net Profit')
    )
    if not ni_dict:
        return False

    dates = qpnl.get('dates', [])
    needed = quarters + 1
    ni_vals = []
    for d in dates:
        v = ni_dict.get(d)
        if v is not None and not pd.isna(v):
            try:
                val = float(v)
                ni_vals.append(val)
                if len(ni_vals) == needed:
                    break
            except (ValueError, TypeError):
                pass

    if len(ni_vals) < needed:
        return False

    # 1. Must be strictly profitable (> 0) in all checked quarters
    for v in ni_vals:
        if v <= 0:
            return False

    # 2. Must be strictly increasing QoQ (newest-first: ni_vals[0] > ni_vals[1] > ni_vals[2])
    for i in range(quarters):
        if ni_vals[i] <= ni_vals[i + 1]:
            return False

    return True


# =========================================================================
# TECHNICAL INDICATORS
# =========================================================================
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Standard Wilder's RSI matching TradingView and Zerodha Kite."""
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
    """
    Computes Yearly Pivot & R1 from the PRIOR completed calendar year's OHLC,
    held constant across the current year's daily rows.
    """
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
    """
    Cleans OHLCV columns, ensures DatetimeIndex, resamples to weekly, computes
    weekly EMAs (10, 30, 40), Daily RSI (14), Yearly R1, and maps weekly status lookahead-free.
    """
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

    # Stacked check: 10 EMA > 30 EMA > 40 EMA
    w_df['w_stacked'] = (w_df['w_ema10'] > w_df['w_ema30']) & (w_df['w_ema30'] > w_df['w_ema40'])

    # Weekly close below 30 EMA check
    w_df['w_close_below_30ema'] = w_df['close'] < w_df['w_ema30']

    # Map weekly state to daily index lookahead-free using prior completed week
    w_period = df_clean.index.to_period('W-FRI')
    w_stacked_shifted = w_df['w_stacked'].shift(1).to_period('W-FRI')
    w_ema30_shifted = w_df['w_ema30'].shift(1).to_period('W-FRI')

    df_clean['weekly_ema_stacked'] = w_period.map(w_stacked_shifted).fillna(False).astype(bool)
    df_clean['weekly_ema30'] = w_period.map(w_ema30_shifted).to_numpy(dtype=float)

    # Compute Daily RSI
    df_clean['daily_rsi'] = compute_rsi(df_clean['close'], DAILY_RSI_PERIOD)
    df_clean['rsi_crossed_85'] = (df_clean['daily_rsi'] > DAILY_RSI_THRESHOLD) & (df_clean['daily_rsi'].shift(1) <= DAILY_RSI_THRESHOLD)

    # Compute Yearly Pivot & R1
    piv, r1 = _compute_yearly_pivot_r1(df_clean)
    df_clean['yearly_pivot'] = piv
    df_clean['yearly_r1'] = r1
    df_clean['Yearly_R1'] = r1

    # Format date strings
    df_clean['date_str'] = df_clean.index.strftime('%Y-%m-%d')
    w_df['date_str'] = w_df.index.strftime('%Y-%m-%d')

    return df_clean, w_df


def simulate_trades(df: pd.DataFrame):
    """
    Executes walk-forward trade simulation across daily bars with:
    1. Buy Signal: Daily RSI crosses above 85 AND Weekly EMAs stacked (10 > 30 > 40).
    2. Yearly R1 Rule:
       - If Close > Yearly R1 on signal bar -> Buy at High of candle immediately.
       - If Close <= Yearly R1 -> Armed Buy Trigger; buy at High of the first daily candle
         that closes above Yearly R1.
    3. Trailing Exit: Intrabar 100% Target Profit OR Weekly 30 EMA Breakdown Exit.
    """
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

    # Map weekly bars for breakdown tracking
    w_close = w_df['close'].to_numpy(dtype=float)
    w_low = w_df['low'].to_numpy(dtype=float)
    w_ema30 = w_df['w_ema30'].to_numpy(dtype=float)
    w_indices = w_df.index

    long_entry = np.zeros(n, dtype=bool)
    signal = np.zeros(n, dtype=bool)
    tp_pct_arr = np.full(n, np.nan)
    sl_pct_arr = np.full(n, DEFAULT_SL_PCT)
    trades = []

    # State tracking
    state = "IDLE"  # "IDLE", "AWAITING_R1_CLOSE", "AWAITING_BREAKOUT", "IN_TRADE"
    signal_high = None
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
            # Identify any completed weekly candle up to date cur_date
            w_past = np.where(w_indices <= cur_date)[0]
            if len(w_past) > 0:
                cur_w_idx = w_past[-1]
                if cur_w_idx > last_checked_w_idx and cur_w_idx >= 0:
                    if w_close[cur_w_idx] < w_ema30[cur_w_idx]:
                        # Weekly close below 30 EMA: arm that weekly candle's low
                        armed_sl_low = w_low[cur_w_idx] if armed_sl_low is None else min(armed_sl_low, w_low[cur_w_idx])
                    else:
                        # Price closed back above 30 EMA -> breakdown disarmed
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

                # Check Yearly R1 condition:
                # If candle close > Yearly R1: Buy at High of this candle immediately
                if not np.isnan(r1[i]) and close[i] > r1[i]:
                    if NEXT_BAR_BREAKOUT:
                        signal_high = high[i]
                        state = "AWAITING_BREAKOUT"
                        i += 1
                        continue
                    else:
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

                        # Check intrabar 100% TP on entry candle itself
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
                    # Candle is NOT above Yearly R1 -> Becomes an Armed Buy Trigger!
                    state = "AWAITING_R1_CLOSE"
                    r1_trigger_idx = i

            i += 1
            continue

        elif state == "AWAITING_R1_CLOSE":
            # If another RSI cross occurs while awaiting, refresh trigger
            if rsi_cross[i] and weekly_stacked[i]:
                r1_trigger_idx = i

            # Optional timeout check
            if MAX_R1_TRIGGER_WAIT_DAYS > 0 and (i - r1_trigger_idx) >= MAX_R1_TRIGGER_WAIT_DAYS:
                state = "IDLE"
                i += 1
                continue

            # Optional weekly stack check
            if REQUIRE_WEEKLY_STACK_ON_R1_ENTRY and not weekly_stacked[i]:
                state = "IDLE"
                i += 1
                continue

            # Buy condition: daily candle closes above Yearly R1
            if not np.isnan(r1[i]) and close[i] > r1[i]:
                # We buy at the HIGH of this candle
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

        elif state == "AWAITING_BREAKOUT":
            if high[i] > signal_high:
                # Next bar broke signal high
                trade_entry_idx = i
                entry_price = signal_high if open_[i] <= signal_high else open_[i]
                tp_price = entry_price * (1.0 + TP_PCT / 100.0)
                long_entry[i] = True
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
            else:
                state = "IDLE"
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

    # ------------------------------------------------------------
    # FUNDAMENTAL PRE-FILTER GATE
    # ------------------------------------------------------------
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

    # QoQ Net Profit Growth Gate:
    # Must be profitable (> 0) and increasing for the last QOQ_PROFIT_GROWTH_QUARTERS (2 quarters)
    if REQUIRE_QOQ_PROFIT_GROWTH and symbol:
        if not check_qoq_profit_increasing(symbol, quarters=QOQ_PROFIT_GROWTH_QUARTERS):
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

screen = backtest

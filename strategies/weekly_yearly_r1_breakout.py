"""
Weekly Yearly-R1 Breakout Strategy (RSI > 80 + 400% TP & 30 EMA Trailing Exit)
===================================================================================================
Timeframe: WEEKLY candles (automatically resamples daily data to weekly W-FRI).

STRATEGY RULES:

1. FUNDAMENTAL PRE-FILTER GATE:
   - Profitability Gate:
     * Strictly requires the company's Net Profit / Net Income to be profitable (> 0)
       for each of the last 2 quarters.
     * Loss-making companies (<= 0) are rejected immediately.
   - Quarterly YoY Profit Growth Gate (NEW):
     * Strictly requires the company's previous 3 quarters to show Year-over-Year (YoY)
       quarterly profit growth strictly above 25% (YoY Growth >= 25.0%).
     * For each of the last 3 quarters, compares net profit against the same quarter of the
       previous year (4 quarters prior / ~365 days prior).
     * Requires both base and current quarters to be strictly profitable (> 0).
   - Configurable pre-filters (Market Cap, ROE, PE, Debt/Equity) - disabled by default (0).

2. YEARLY PIVOT & R1:
   Computed from the PRIOR completed calendar year's High, Low, and Close:
       Pivot = (High_prev_year + Low_prev_year + Close_prev_year) / 3
       R1    = 2 * Pivot - Low_prev_year
   Held constant across all weekly candles of the current calendar year.

3. BUY QUALIFICATION CANDLE:
   A weekly candle qualifies as a candidate when:
   - High crosses above that calendar year's Yearly R1:
     (high[i] > r1[i] and high[i-1] <= r1[i-1]).
   - RSI filter: Weekly 14-period RSI must be strictly above 80 (RSI > 80.0).
   (No volume confirmation is required.)

4. ENTRY TRIGGER (Next Candle Breaks High):
   - We do not buy immediately on the qualifying candle; we place a buy stop at the
     HIGH of this qualifying candle.
   - Entry triggers when the NEXT immediate weekly candle breaks above this high
     (high[i+1] > qualifying_high).
   - Entry Price = HIGH of the qualifying candle (or open[i+1] if gapped above).

5. TARGET PROFIT & EXIT CRITERIA (Established Trades):
   - Criteria 1: Target Profit of 400% (+400.0% gain from entry price: tp_price = entry_price * 5.0).
     Triggers intrabar when high >= tp_price.
   - Criteria 2: 30 EMA Breakdown Exit:
     When a weekly candle closes below the 30-period EMA (close < ema30), its low becomes the armed low.
     If the low of this candle gets broken by a subsequent candle (low < armed_low), exit immediately!
     (If price closes back above 30 EMA without breaking the low, the breakdown is disarmed).
"""

import os
import json
import numpy as np
import pandas as pd

# ============================================================
# CONFIG - FUNDAMENTAL PRE-FILTER GATE (0 / False disables a check)
# ============================================================
MIN_MARKET_CAP_CR = 0
MIN_ROE = 0.0
MAX_PE = 0.0
MAX_DEBT_TO_EQUITY = 0.0

REQUIRE_PROFITABLE = True             # Strictly require Net Profit to be profitable (> 0)
PROFITABLE_QUARTERS = 2               # Number of recent quarters that must be profitable (> 0)

REQUIRE_YOY_PROFIT_GROWTH = True      # Require previous 3 quarters YoY quarterly profit growth > 25%
MIN_YOY_PROFIT_GROWTH_PCT = 25.0      # Minimum YoY profit growth % (> 25.0%)
YOY_QUARTERS_TO_CHECK = 3             # Number of previous quarters to check (3 quarters)
STRICT_ALL_3_QUARTERS = False         # False: all available YoY pairs of last 3 quarters must be >25% (handles 5-6 quarter data cache); True: strictly requires 3 full pairs

# ============================================================
# CONFIG - SIGNAL / RSI / EXITS
# ============================================================
RSI_PERIOD = 14                  # standard Wilder RSI period
MIN_RSI = 80.0                   # candle qualifying for a buy must have RSI > 80
EMA_PERIOD = 30                  # weekly close EMA used for trend trailing exit
TP_PCT = 400.0                   # fixed target profit in % (400% profit target)
DEFAULT_SL_PCT = 10.0            # fallback stop loss % for scalar consumers
MAX_HOLD_BARS = 250              # safety cap (weeks) so a trade cannot run indefinitely


# ============================================================
# FUNDAMENTAL HELPERS
# ============================================================
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
    """
    Strictly verifies whether a stock's Net Profit / Income is strictly profitable (> 0)
    for each of the last `quarters` quarters.
    Returns False if quarterly data is missing, or if any quarter was loss-making (<= 0).
    Does NOT require profits to be increasing.
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
        metrics.get('Net Profit') or
        metrics.get('Net Income From Continuing Operation Net Minority Interest') or
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

    # Strictly profitable (> 0) in all checked quarters
    for v in ni_vals:
        if v <= 0:
            return False

    return True


def check_quarterly_yoy_growth(symbol: str, quarters: int = 3, min_growth_pct: float = 25.0, strict_all: bool = False) -> bool:
    """
    Verifies that the stock's previous `quarters` quarters show Year-over-Year (YoY)
    quarterly profit growth strictly above `min_growth_pct` (e.g. > 25.0%).

    For each of the most recent `quarters` (e.g. 3 quarters):
    - Identifies the same quarter 1 year ago (4 quarters prior / ~365 days prior).
    - Requires current quarter Net Income / Profit to be strictly positive (> 0).
    - Requires prior year quarter Net Income / Profit to be strictly positive (> 0).
    - Calculates YoY growth: ((curr_profit - prior_profit) / prior_profit) * 100.0
    - Enforces YoY growth >= min_growth_pct (> 25%).
    - If any evaluated YoY quarter fails to meet the threshold, returns False immediately.

    If strict_all is True: requires all `quarters` (3 quarters) to have complete YoY data.
    If strict_all is False: requires all available YoY pairs (at least 1) to pass > 25%.
    """
    if not symbol or quarters <= 0:
        return False
    stmt = _load_statement_data(symbol)
    if not stmt:
        return False

    qpnl = stmt.get('quarterly_pnl', {})
    dates = qpnl.get('dates', [])
    metrics = qpnl.get('metrics', {})

    ni_dict = (
        metrics.get('Net Income') or
        metrics.get('Net Income Common Stockholders') or
        metrics.get('Normalized Income') or
        metrics.get('Net Income Including Noncontrolling Interests') or
        metrics.get('Net Profit') or
        metrics.get('Net Income From Continuing Operation Net Minority Interest') or
        metrics.get('Profit After Tax')
    )
    if not ni_dict:
        return False

    valid_q = []
    for d in dates:
        v = ni_dict.get(d)
        if v is not None and not pd.isna(v):
            try:
                valid_q.append((pd.to_datetime(d), float(v)))
            except (ValueError, TypeError):
                pass

    # Sort descending (most recent quarter first)
    valid_q = sorted(valid_q, key=lambda x: x[0], reverse=True)
    if not valid_q:
        return False

    num_to_check = min(quarters, len(valid_q))
    evaluated_count = 0

    for i in range(num_to_check):
        curr_dt, curr_val = valid_q[i]

        # Look for the same quarter 1 year prior (~365 days prior, 300 to 430 days)
        prior_candidates = [q for q in valid_q if 300 <= (curr_dt - q[0]).days <= 430]
        if not prior_candidates and i + 4 < len(valid_q):
            prior_candidates = [valid_q[i + 4]]

        if not prior_candidates:
            if strict_all:
                return False
            continue

        prior_dt, prior_val = prior_candidates[0]

        # Both quarters must be strictly profitable (> 0)
        if curr_val <= 0 or prior_val <= 0:
            return False

        yoy_growth = ((curr_val - prior_val) / prior_val) * 100.0
        if yoy_growth < min_growth_pct:
            return False

        evaluated_count += 1

    if strict_all and evaluated_count < quarters:
        return False

    return evaluated_count > 0


# ============================================================
# TECHNICAL INDICATORS & RESAMPLING
# ============================================================
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


def simulate_trades(df: pd.DataFrame):
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)
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

    state = "IDLE"  # "IDLE", "AWAITING_BREAKOUT", "IN_TRADE"
    qualifying_high = None

    trade_entry_idx = None
    entry_price = None
    tp_price = None
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
            # 2. Weekly RSI > 80
            crossed_now = high[i] > r1[i]
            was_below = high[i - 1] <= r1[i - 1] if not np.isnan(r1[i - 1]) else False
            rsi_ok = rsi[i] > MIN_RSI

            if crossed_now and was_below and rsi_ok:
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
                state = "IN_TRADE"
                ema30_armed_low = None

                long_entry[i] = True
                tp_pct_arr[i] = TP_PCT

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
                        "exit_reason": f"Target Profit ({int(TP_PCT)}% Same Bar)",
                        "mae_pct": round(float(mae), 2),
                        "mfe_pct": round(float(mfe), 2),
                        "is_open": False,
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
            mae = max(mae, (entry_price - low[i]) / entry_price * 100.0)
            mfe = max(mfe, (high[i] - entry_price) / entry_price * 100.0)

            bars_in_trade = i - trade_entry_idx

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
                })
                state = "IDLE"
                i += 1
                continue

            # Check 1: Target Profit
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

    if n < (EMA_PERIOD + RSI_PERIOD + 5):
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

    # Profitability Gate: Must be strictly profitable (> 0) for the last PROFITABLE_QUARTERS (2 quarters)
    if REQUIRE_PROFITABLE and symbol:
        if not check_profitable(symbol, quarters=PROFITABLE_QUARTERS):
            return empty_res

    # Quarterly YoY Profit Growth Gate: Previous 3 quarters YoY quarterly growth must be > 25%
    if REQUIRE_YOY_PROFIT_GROWTH and symbol:
        if not check_quarterly_yoy_growth(symbol, quarters=YOY_QUARTERS_TO_CHECK, min_growth_pct=MIN_YOY_PROFIT_GROWTH_PCT, strict_all=STRICT_ALL_3_QUARTERS):
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

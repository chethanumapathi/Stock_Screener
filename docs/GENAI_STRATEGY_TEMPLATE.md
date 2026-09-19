# GenAI Prompt & Sandbox Strategy Coding Guide

Use this guide and master prompt to draft quantitative and techno-fundamental strategies using any Generative AI (**ChatGPT**, **Claude**, **Gemini**, **DeepSeek**) that run 100% seamlessly in the **ChethanQuant Stock Screener & Backtester** sandbox.

---

## 📋 Master Prompt for GenAI (Copy & Paste to AI)

Copy everything inside the block below and paste it into your AI of choice:

```text
You are an expert quantitative Python developer. I need a quantitative trading strategy script written in Python for my custom Stock Screener and Backtesting Sandbox engine.

You MUST strictly follow these sandbox architecture specifications:

1. ENVIRONMENT & LIBRARIES:
   - Available standard libraries: `numpy as np`, `pandas as pd`, `math`, `datetime`, `timedelta`.
   - Available built-in global helper functions:
     * `get_stock_fundamentals(symbol, fetch_online=False)`: Returns dictionary of financial ratios (pe, forwardPE, pb, roe, roa, debtToEquity, currentRatio, quickRatio, operatingMargin, profitMargin, dividendYield, marketCapCr, sector, industry).
     * `get_stock_statement(symbol, fetch_online=False)`: Returns full financial statements dictionary with `quarterly_pnl`, `yearly_pnl`, `balance_sheet`, and `cashflow`.
     * `get_market_cap_cr(symbol, fetch_online=False)`: Returns market capitalization in ₹ Crores.
   - The primary input parameter is a single pandas DataFrame: `df`.

2. DATAFRAME STRUCTURE (`df`):
   - Guaranteed price & volume columns: `open`, `high`, `low`, `close`, `volume`, `prev_close`, `date`.
   - Guaranteed identification & market cap:
     * `symbol` / `Symbol`: Stock ticker string (e.g. 'RELIANCE', 'COALINDIA', 'TCS').
     * `Market_Cap_Cr`: Market capitalization in ₹ Crores (float).
   - Pre-attached fundamental ratio columns (when available in local cache):
     * `PE`: Trailing 12M Price-to-Earnings ratio.
     * `Forward_PE`: Forward P/E ratio.
     * `PB`: Price-to-Book ratio.
     * `ROE`: Return on Equity (%) (e.g. 18.5 for 18.5%).
     * `ROA`: Return on Assets (%) (e.g. 8.2 for 8.2%).
     * `Debt_To_Equity`: Debt-to-Equity solvency ratio (e.g. 0.35).
     * `Operating_Margin`: Operating profit margin (%).
     * `Profit_Margin`: Net profit margin (%).
     * `Dividend_Yield`: Dividend yield (%).
   - Timeframe: `df` is ALREADY at the user's selected timeframe (e.g. Daily `1d`, Hourly `1h`, 15m).
   - CRITICAL TIMEFRAME RULE: All indicators (50 EMA, 200 EMA, RSI, OBV, etc.) must calculate DIRECTLY on the incoming DataFrame's candles (`df['close']`, `df['high']`, `df['low']`, `df['volume']`). Do NOT forcibly resample `df` unless multi-timeframe aggregation is explicitly asked.

3. TWO-STAGE ARCHITECTURE: FUNDAMENTAL GATE -> TECHNICAL TRIGGER
   Always separate strategy logic into two distinct steps:
   - STEP 1 (FUNDAMENTAL PRE-FILTER GATE):
     Before running any technical indicator math or loop simulation, evaluate all fundamental criteria.
     If a stock fails Market Cap, Valuation (P/E), Profitability (ROE), Leverage (Debt-to-Equity), or QoQ Sales Growth, immediately exit and return an empty result:
     ```python
     empty_res = {
         "trades": [],
         "long_entry": pd.Series(False, index=df.index),
         "entries": pd.Series(False, index=df.index),
         "signal": pd.Series(False, index=df.index),
         "tp_pct": pd.Series(np.nan, index=df.index),
         "sl_pct": pd.Series(np.nan, index=df.index),
         "df": df
     }
     ```
   - STEP 2 (TECHNICAL STRATEGY LOGIC):
     Executes ONLY on stocks that successfully passed Step 1. Computes technical indicators, entry triggers, and trade simulation.

4. FUNDAMENTAL FILTERING IMPLEMENTATION:
   - Configurable Variables:
     ```python
     MIN_MARKET_CAP_CR = 2000         # Min Market Cap (₹ Cr, 0 to disable)
     MIN_ROE = 15.0                   # Min Return on Equity % (0 to disable)
     MAX_PE = 40.0                    # Max Trailing P/E (0 to disable)
     MAX_DEBT_TO_EQUITY = 1.0         # Max Debt-to-Equity ratio (0 to disable)
     REQUIRE_QOQ_SALES_GROWTH = True  # Require last N quarters sales increasing QoQ
     QOQ_QUARTERS = 4                 # Consecutive quarters to check
     ```
   - Standard QoQ Sales Growth Helper:
     ```python
     def check_quarterly_sales_increasing(symbol: str, quarters: int = 4) -> bool:
         """Strictly verifies that quarterly sales / total revenue has increased QoQ for the last N quarters."""
         if not symbol:
             return False
         try:
             stmt = get_stock_statement(symbol, fetch_online=False)
             if not stmt:
                 return False
             qpnl = stmt.get('quarterly_pnl', {})
             metrics = qpnl.get('metrics', {})
             rev_dict = metrics.get('Total Revenue') or metrics.get('Operating Revenue')
             if not rev_dict:
                 return False
             dates = qpnl.get('dates', [])
             valid_revs = []
             for d in dates:
                 val = rev_dict.get(d)
                 if val is not None and not pd.isna(val) and float(val) > 0:
                     valid_revs.append(float(val))
                     if len(valid_revs) == quarters:
                         break
             if len(valid_revs) < quarters:
                 return False
             # valid_revs is newest-first; reverse to get chronological (oldest to newest)
             rev_chronological = list(reversed(valid_revs))
             for i in range(1, len(rev_chronological)):
                 if rev_chronological[i] <= rev_chronological[i - 1]:
                     return False
             return True
         except Exception:
             return False
     ```
   - Standard QoQ Net Profit Positive Helper:
     ```python
     def check_quarterly_profit_positive(symbol: str, quarters: int = 2) -> bool:
         """Verifies that net profit / income was positive for the last N consecutive quarters."""
         if not symbol or quarters <= 0:
             return False
         try:
             stmt = get_stock_statement(symbol, fetch_online=False)
             if not stmt:
                 return False
             qpnl = stmt.get('quarterly_pnl', {})
             metrics = qpnl.get('metrics', {})
             # In financial statements, net profit is reported under 'Net Income'
             profit_dict = (
                 metrics.get('Net Income')
                 or metrics.get('Net Income Common Stockholders')
                 or metrics.get('Normalized Income')
                 or metrics.get('Net Income Including Noncontrolling Interests')
                 or metrics.get('Net Profit')
                 or metrics.get('Profit After Tax')
                 or metrics.get('PAT')
             )
             if not profit_dict:
                 return False
             dates = qpnl.get('dates', [])
             valid_profits = []
             for d in dates:
                 val = profit_dict.get(d)
                 if val is not None and not pd.isna(val):
                     try:
                         fval = float(val)
                         valid_profits.append(fval)
                         if len(valid_profits) == quarters:
                             break
                     except (ValueError, TypeError):
                         pass
             if len(valid_profits) < quarters:
                 return False
             return all(p > 0 for p in valid_profits)
         except Exception:
             return False
     ```

5. STANDARD INDICATOR FORMULAS:
   - Exponential Moving Average (EMA) - matches TradingView & Zerodha Kite:
     ```python
     def compute_ema(series: pd.Series, period: int) -> np.ndarray:
         return series.ewm(span=period, adjust=False).mean().to_numpy(dtype=float)
     ```
   - On-Balance Volume (OBV):
     ```python
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
     ```
   - Prior Completed Calendar Month Pivots (held constant across current month's rows):
     Group by calendar month `to_period('M')` and use `.shift(1)` to reference prior month's OHLC.

6. ENTRY & TRADE SIMULATION:
   - Implement `_simulate_one_trade(low, high, close, opn, ema, entry_idx, entry_price, tp_price, ...)` walk-forward loop from `entry_idx + 1` to `n`:
     - Checks Stop Loss (e.g. trailing 50 EMA pullback low, or initial SL).
     - Checks Target Profit (`high >= tp_price`).
     - Tracks Maximum Adverse Excursion (`mae_pct`) and Maximum Favorable Excursion (`mfe_pct`).
     - Returns: `exit_idx, exit_price, exit_reason, mae_pct, mfe_pct`.
   - Implement `simulate_trades(df)` returning a pandas DataFrame of trades.

7. REQUIRED `backtest(df)` RETURN DICTIONARY:
   Must return a dict containing:
   - `"trades"`: list of trade dicts:
     `{"entry_date": str, "entry_price": float, "exit_date": str, "exit_price": float, "exit_reason": str, "mae_pct": float, "mfe_pct": float, "is_open": bool}`
   - `"long_entry"`: boolean `pd.Series` (True on entry candles)
   - `"entries"`: boolean `pd.Series` (identical to `long_entry`)
   - `"signal"`: boolean `pd.Series` (setup signal)
   - `"tp_pct"`: `pd.Series` or float (Target Profit %)
   - `"sl_pct"`: `pd.Series` or float (Stop Loss %)
   - `"df"`: the DataFrame with newly calculated indicators appended for table display.

8. SCREENER ALIAS:
   At the very bottom of the file, always include:
   ```python
   screen = backtest
   ```

--------------------------------------------------
MY STRATEGY RULES TO IMPLEMENT:
[Describe your strategy rules here: e.g. fundamental criteria, technical indicators, entry triggers, TP %, SL rules]
--------------------------------------------------
```

---

## 🐍 Universal Python Boilerplate Template

Below is the complete, runnable starter template demonstrating both **Fundamental Filtering** and **Technical Price Action**:

```python
"""
Techno-Fundamental Quantitative Strategy Template (Universal Screener & Backtester)
===================================================================================
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).
Enforces a two-stage architecture:
  Stage 1: Fundamental Pre-Filter Gate (Market Cap, ROE, P/E, QoQ Sales Growth)
  Stage 2: Technical Signal Generation & Walk-Forward Trailing SL Simulation
"""

import numpy as np
import pandas as pd

# -------------------------------------------------------------------------
# 1. Configurable Fundamental Filters
# -------------------------------------------------------------------------
MIN_MARKET_CAP_CR = 2000.0        # Minimum Market Cap in ₹ Crores (0 to disable)
MIN_ROE = 15.0                     # Minimum Return on Equity % (0 to disable)
MAX_PE = 40.0                      # Maximum Trailing P/E (0 to disable)
MAX_DEBT_TO_EQUITY = 1.0           # Maximum Debt to Equity ratio (0 to disable)
REQUIRE_QOQ_SALES_GROWTH = True    # Strictly require last N quarters sales increasing QoQ
QOQ_QUARTERS = 4                   # Number of consecutive quarters to check

# -------------------------------------------------------------------------
# 2. Configurable Technical Variables
# -------------------------------------------------------------------------
EMA_FAST = 20                      # Fast Moving Average period
EMA_SLOW = 50                      # Slow Moving Average period (SL trailing reference)
TP_PCT = 25.0                      # Target Profit % from entry price
DEFAULT_SL_PCT = 5.0               # Initial Stop Loss % fallback


# -------------------------------------------------------------------------
# Fundamental Helper: Consecutive QoQ Sales Growth
# -------------------------------------------------------------------------
def check_quarterly_sales_increasing(symbol: str, quarters: int = 4) -> bool:
    """
    Strictly verifies whether a stock's total revenue / sales has increased
    quarter-over-quarter (QoQ) consecutively for the last `quarters` reports.
    Returns False immediately if data is missing or if any quarter had lower revenue.
    """
    if not symbol:
        return False
    try:
        stmt = None
        if 'get_stock_statement' in globals() and callable(globals()['get_stock_statement']):
            stmt = globals()['get_stock_statement'](symbol, fetch_online=False)
        if not stmt:
            return False

        qpnl = stmt.get('quarterly_pnl', {})
        metrics = qpnl.get('metrics', {})
        rev_dict = metrics.get('Total Revenue') or metrics.get('Operating Revenue')
        if not rev_dict:
            return False

        dates = qpnl.get('dates', [])
        valid_revenues = []
        for d in dates:
            val = rev_dict.get(d)
            if val is not None and not pd.isna(val) and float(val) > 0:
                valid_revenues.append(float(val))
                if len(valid_revenues) == quarters:
                    break

        if len(valid_revenues) < quarters:
            return False

        # valid_revenues is newest-first; reverse to get chronological (oldest to newest)
        rev_chronological = list(reversed(valid_revenues))
        for i in range(1, len(rev_chronological)):
            if rev_chronological[i] <= rev_chronological[i - 1]:
                return False  # Dropped compared to previous quarter
        return True
    except Exception:
        return False


# -------------------------------------------------------------------------
# Technical Indicators (Standard TradingView / Kite Formulas)
# -------------------------------------------------------------------------
def compute_ema(series: pd.Series, period: int) -> np.ndarray:
    """Standard Exponential Moving Average calculated directly on selected timeframe."""
    return series.ewm(span=period, adjust=False).mean().to_numpy(dtype=float)


def compute_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """Standard On-Balance Volume."""
    obv = np.zeros(len(close))
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]
    return obv


# -------------------------------------------------------------------------
# Signal Generation Logic
# -------------------------------------------------------------------------
def _compute_signals(df: pd.DataFrame):
    n = len(df)
    close = df['close'].to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    volume = df['volume'].to_numpy(dtype=float)

    ema_fast = compute_ema(df['close'], EMA_FAST)
    ema_slow = compute_ema(df['close'], EMA_SLOW)
    obv = compute_obv(close, volume)

    # Example Buy Condition: Fast EMA crosses above Slow EMA with price above Slow EMA
    bullish_cross = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if ema_fast[i] > ema_slow[i] and ema_fast[i - 1] <= ema_slow[i - 1] and close[i] > ema_slow[i]:
            bullish_cross[i] = True

    entries = bullish_cross.copy()
    entry_price_arr = np.where(entries, close, np.nan)

    return entries, entry_price_arr, ema_fast, ema_slow, obv


# -------------------------------------------------------------------------
# Walk-Forward Trade Simulator (Trailing SL & Target Profit)
# -------------------------------------------------------------------------
def _simulate_one_trade(low, high, close, opn, ema_ref, entry_idx, entry_price, tp_price):
    """
    Simulates a single trade lifecycle walking forward from entry_idx + 1:
    - Target Profit (TP) triggered when high reaches tp_price.
    - Trailing Stop Loss (armed when a bar closes below EMA, triggered on breach of that low).
    - Tracks Maximum Adverse Excursion (MAE) and Maximum Favorable Excursion (MFE).
    """
    n = len(close)
    armed_low = None
    min_low = low[entry_idx]
    max_high = high[entry_idx]

    for i in range(entry_idx + 1, n):
        min_low = min(min_low, low[i])
        max_high = max(max_high, high[i])

        # 1. Check Trailing SL breach
        if armed_low is not None and low[i] < armed_low:
            exit_price = min(armed_low, opn[i]) if opn[i] < armed_low else armed_low
            mae_pct = (min_low - entry_price) / entry_price * 100.0
            mfe_pct = (max_high - entry_price) / entry_price * 100.0
            return i, exit_price, "Stop Loss (Trailing 50 EMA Low)", mae_pct, mfe_pct

        # 2. Check Target Profit hit
        if high[i] >= tp_price:
            exit_price = tp_price
            mae_pct = (min_low - entry_price) / entry_price * 100.0
            mfe_pct = (max_high - entry_price) / entry_price * 100.0
            return i, exit_price, "Target Profit (TP)", mae_pct, mfe_pct

        # 3. Arm / Ratchet trailing stop loss if bar closes below reference EMA
        if not np.isnan(ema_ref[i]) and close[i] < ema_ref[i]:
            armed_low = low[i]

    # End of data / Trade still running
    mae_pct = (min_low - entry_price) / entry_price * 100.0
    mfe_pct = (max_high - entry_price) / entry_price * 100.0
    return n - 1, close[-1], "End of Data", mae_pct, mfe_pct


# -------------------------------------------------------------------------
# Standalone Simulation Function
# -------------------------------------------------------------------------
def simulate_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a pandas DataFrame of all simulated trades for detailed inspection."""
    res = backtest(df)
    trades = res.get("trades", [])
    if not trades:
        return pd.DataFrame(columns=["Entry Date", "Entry Price", "Exit Date", "Exit Price", "Exit Reason", "MAE (%)", "MFE (%)", "PnL (%)"])

    rows = []
    for t in trades:
        rows.append({
            "Entry Date": t["entry_date"],
            "Entry Price": t["entry_price"],
            "Exit Date": t["exit_date"],
            "Exit Price": t["exit_price"],
            "Exit Reason": t["exit_reason"],
            "MAE (%)": t["mae_pct"],
            "MFE (%)": t["mfe_pct"],
            "PnL (%)": round((t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100.0, 2),
        })
    return pd.DataFrame(rows)


# -------------------------------------------------------------------------
# Main Backtest Entry Point
# -------------------------------------------------------------------------
def backtest(df: pd.DataFrame) -> dict:
    df = df.copy()

    # =========================================================================
    # STEP 1: FUNDAMENTAL PRE-FILTER GATE
    # Reject non-qualifying stocks immediately BEFORE running any technical logic.
    # =========================================================================
    symbol = None
    for c in ['symbol', 'Symbol', 'SYMBOL', 'ticker', 'Ticker']:
        if c in df.columns:
            s_vals = df[c].dropna()
            if not s_vals.empty:
                symbol = str(s_vals.iloc[-1]).upper()
                break

    empty_res = {
        "trades": [],
        "long_entry": pd.Series(False, index=df.index, name="long_entry"),
        "entries": pd.Series(False, index=df.index, name="entries"),
        "signal": pd.Series(False, index=df.index, name="signal"),
        "tp_pct": pd.Series(np.nan, index=df.index, name="tp_pct"),
        "sl_pct": pd.Series(np.nan, index=df.index, name="sl_pct"),
        "df": df
    }

    # 1. Market Cap Filter
    if 'Market_Cap_Cr' in df.columns:
        mcap = df['Market_Cap_Cr'].iloc[-1]
        if mcap is not None and not np.isnan(mcap) and MIN_MARKET_CAP_CR > 0 and mcap < MIN_MARKET_CAP_CR:
            return empty_res

    # 2. Key Fundamental Ratios Filter (P/E, ROE, Debt-to-Equity)
    # Ratios are pre-attached as columns on df or fetched via get_stock_fundamentals(symbol)
    roe = df['ROE'].iloc[-1] if 'ROE' in df.columns else None
    pe = df['PE'].iloc[-1] if 'PE' in df.columns else None
    de = df['Debt_To_Equity'].iloc[-1] if 'Debt_To_Equity' in df.columns else None

    if MIN_ROE > 0 and roe is not None and not np.isnan(roe) and roe < MIN_ROE:
        return empty_res
    if MAX_PE > 0 and pe is not None and not np.isnan(pe) and pe > MAX_PE:
        return empty_res
    if MAX_DEBT_TO_EQUITY > 0 and de is not None and not np.isnan(de) and de > MAX_DEBT_TO_EQUITY:
        return empty_res

    # 3. QoQ Sales Growth Filter (checks last 4 quarterly statements)
    if REQUIRE_QOQ_SALES_GROWTH and symbol:
        if not check_quarterly_sales_increasing(symbol, quarters=QOQ_QUARTERS):
            return empty_res

    # =========================================================================
    # STEP 2: TECHNICAL STRATEGY LOGIC (runs ONLY on fundamentally qualified stocks)
    # =========================================================================

    # Standardize column casing
    clean_cols = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow in ['open', 'high', 'low', 'close', 'volume', 'prev_close', 'date', 'market_cap_cr'] and clow not in clean_cols.values():
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
    entries, entry_price_arr, ema_fast, ema_slow, obv = _compute_signals(df)

    close = df['close'].to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    opn = df['open'].to_numpy(dtype=float)

    # 3. Simulate Trades with Trailing SL
    trades = []
    sl_pct_arr = np.full(n, DEFAULT_SL_PCT)
    tp_pct_arr = np.full(n, TP_PCT)

    date_strs = df['date'].astype(str).values if 'date' in df.columns else df.index.astype(str).values

    for idx in np.where(entries)[0]:
        ep = entry_price_arr[idx]
        tp_price = ep * (1.0 + TP_PCT / 100.0)
        ex_idx, ex_p, reason, mae_pct, mfe_pct = _simulate_one_trade(low, high, close, opn, ema_slow, idx, ep, tp_price)

        trades.append({
            "entry_date": str(date_strs[idx])[:10],
            "entry_price": round(float(ep), 2),
            "exit_date": str(date_strs[ex_idx])[:10],
            "exit_price": round(float(ex_p), 2),
            "exit_reason": reason,
            "mae_pct": round(float(mae_pct), 2),
            "mfe_pct": round(float(mfe_pct), 2),
            "is_open": (reason == "End of Data")
        })
        if ep > 0:
            sl_pct_arr[idx] = round(abs(ep - ex_p) / ep * 100.0, 2)

    # 4. Output DataFrame for Table & Chart Inspection
    out_df = df.copy()
    for col in ['open', 'high', 'low', 'close', 'volume', 'prev_close']:
        if col in out_df.columns and col.capitalize() not in out_df.columns:
            out_df[col.capitalize()] = out_df[col]
    out_df['EMA_Fast'] = ema_fast
    out_df['EMA_Slow'] = ema_slow
    out_df['OBV'] = obv
    out_df['entry_price'] = entry_price_arr
    out_df['Date'] = [str(d)[:10] for d in date_strs]

    return {
        "trades": trades,
        "long_entry": pd.Series(entries, index=df.index, name="long_entry"),
        "entries": pd.Series(entries, index=df.index, name="entries"),
        "signal": pd.Series(entries, index=df.index, name="signal"),
        "tp_pct": pd.Series(tp_pct_arr, index=df.index, name="tp_pct"),
        "sl_pct": pd.Series(sl_pct_arr, index=df.index, name="sl_pct"),
        "df": out_df
    }

# Screener compatibility alias
screen = backtest
```

---

## ⚡ Sandbox Architecture & Rules

### 1. Timeframe Integrity
The incoming DataFrame `df` is **already pre-aggregated** to the user's chosen timeframe (Daily, Hourly, 15-Minute). Compute indicators (EMA, RSI, OBV) directly on `df['close']` so calculations naturally reflect the active timeframe.

### 2. Market Cap Variable
Include `MIN_MARKET_CAP_CR = 2000`. If `Market_Cap_Cr < MIN_MARKET_CAP_CR`, return an empty trades dictionary immediately to skip low-liquidity microcaps.

### 3. Fundamental Data & Financial Statements API
The sandbox provides comprehensive fundamental data via two channels:
- **Pre-Attached Columns on `df`:** `Market_Cap_Cr`, `PE`, `Forward_PE`, `PB`, `ROE`, `ROA`, `Debt_To_Equity`, `Operating_Margin`, `Profit_Margin`, `Dividend_Yield`.
- **Built-in Global Functions:**
  * `get_stock_fundamentals(symbol, fetch_online=False)`: Returns dict of financial ratios, industry, sector.
  * `get_stock_statement(symbol, fetch_online=False)`: Returns full quarterly & annual P&L, balance sheets, and cash flows.

### 4. Two-Stage Architecture (Fundamental Gate $\to$ Technical Trigger)
Always filter stocks by fundamentals at the very start of `backtest(df)` / `screen(df)`. If a stock does not meet fundamental criteria (e.g. Sales falling QoQ, ROE < 15%, Debt/Equity > 1.0), immediately return empty results. This dramatically accelerates scanning and keeps screener tables free of duplicate or unqualified stocks.

### 5. Trailing Stop Loss & Risk Management
When a candle closes below the reference moving average (e.g. 50 EMA), record that candle's `low`. If any subsequent bar breaches below that recorded low, exit the trade immediately. This avoids early fakeouts on intra-bar wicks.

### 6. Return Dictionary Format
Must return a dictionary containing:
- `trades`: list of trade dicts with entry/exit/mae/mfe/is_open.
- `long_entry` & `entries`: boolean `pd.Series`.
- `signal`: boolean `pd.Series`.
- `tp_pct` & `sl_pct`: `pd.Series` or float.
- `df`: the DataFrame with calculated indicators appended.

### 7. Universal Screen Alias
Always end your script with `screen = backtest`. This ensures your strategy runs seamlessly across both the **Quant Screener** and the **Backtest Engine** without modifying a single line of code.

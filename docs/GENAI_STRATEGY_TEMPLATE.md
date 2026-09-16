# GenAI Prompt & Sandbox Strategy Coding Guide

Use this guide and master prompt to draft quantitative strategies using any Generative AI (**ChatGPT**, **Claude**, **Gemini**, **DeepSeek**) that run 100% seamlessly in the **ChethanQuant Stock Screener & Backtester** sandbox.

---

## 📋 Master Prompt for GenAI (Copy & Paste to AI)

Copy everything inside the block below and paste it into your AI of choice:

```text
You are an expert quantitative Python developer. I need a quantitative trading strategy script written in Python for my custom Stock Screener and Backtesting Sandbox engine.

You MUST strictly follow these sandbox architecture specifications:

1. ENVIRONMENT & LIBRARIES:
   - Available libraries: `numpy as np`, `pandas as pd`, `math`, `datetime`.
   - The input parameter is a single pandas DataFrame: `df`.

2. DATAFRAME STRUCTURE (`df`):
   - Guaranteed columns: `open`, `high`, `low`, `close`, `volume`, `prev_close`, `date`, `Market_Cap_Cr`.
   - Index: Chronological (DatetimeIndex or row index).
   - Timeframe: `df` is ALREADY at the user's selected timeframe (e.g. Daily `1d`, Hourly `1h`, 15m).
   - CRITICAL TIMEFRAME RULE: All indicators (50 EMA, 200 EMA, RSI, OBV, etc.) must calculate DIRECTLY on the incoming DataFrame's candles (`df['close']`, `df['high']`, `df['low']`, `df['volume']`). Do NOT forcibly resample `df` unless multi-timeframe aggregation is explicitly asked.

3. MARKET CAP FILTER:
   - Include a top-level configurable variable: `MIN_MARKET_CAP_CR = 2000` (₹ Crores, default 2000). Set to 0 to disable.
   - At the beginning of `backtest(df)`:
     ```python
     if 'Market_Cap_Cr' in df.columns:
         mcap = df['Market_Cap_Cr'].iloc[-1]
         if mcap is not None and not np.isnan(mcap) and MIN_MARKET_CAP_CR > 0 and mcap < MIN_MARKET_CAP_CR:
             return {
                 "trades": [],
                 "long_entry": pd.Series(False, index=df.index),
                 "entries": pd.Series(False, index=df.index),
                 "signal": pd.Series(False, index=df.index),
                 "tp_pct": pd.Series(np.nan, index=df.index),
                 "sl_pct": pd.Series(np.nan, index=df.index),
                 "df": df
             }
     ```

4. STANDARD INDICATOR FORMULAS:
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

5. ENTRY & TRADE SIMULATION:
   - Implement `_simulate_one_trade(low, high, close, opn, ema, entry_idx, entry_price, tp_price, ...)` walk-forward loop from `entry_idx + 1` to `n`:
     - Checks Stop Loss (e.g. trailing 50 EMA pullback low, or initial SL).
     - Checks Target Profit (`high >= tp_price`).
     - Tracks Maximum Adverse Excursion (`mae_pct`) and Maximum Favorable Excursion (`mfe_pct`).
     - Returns: `exit_idx, exit_price, exit_reason, mae_pct, mfe_pct`.
   - Implement `simulate_trades(df)` returning a pandas DataFrame of trades.

6. REQUIRED `backtest(df)` RETURN DICTIONARY:
   Must return a dict containing:
   - `"trades"`: list of trade dicts:
     `{"entry_date": str, "entry_price": float, "exit_date": str, "exit_price": float, "exit_reason": str, "mae_pct": float, "mfe_pct": float, "is_open": bool}`
   - `"long_entry"`: boolean `pd.Series` (True on entry candles)
   - `"entries"`: boolean `pd.Series` (identical to `long_entry`)
   - `"signal"`: boolean `pd.Series` (setup signal)
   - `"tp_pct"`: `pd.Series` or float (Target Profit %)
   - `"sl_pct"`: `pd.Series` or float (Stop Loss %)
   - `"df"`: the DataFrame with newly calculated indicators appended for table display.

7. SCREENER ALIAS:
   At the very bottom of the file, always include:
   ```python
   screen = backtest
   ```

--------------------------------------------------
MY STRATEGY RULES TO IMPLEMENT:
[Describe your strategy rules here: e.g. indicators, entry conditions, exit rules, TP %, SL rules]
--------------------------------------------------
```

---

## 🐍 Universal Python Boilerplate Template

Below is the complete, runnable starter template that satisfies all sandbox requirements:

```python
"""
Custom Quantitative Strategy Template (Universal Screener & Backtester)
========================================================================
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).
All indicators calculate directly on the timeframe selected by the user.
"""

import numpy as np
import pandas as pd

# -------------------------------------------------------------------------
# Configurable Strategy Variables
# -------------------------------------------------------------------------
MIN_MARKET_CAP_CR = 2000      # Minimum Market Cap in ₹ Crores (0 to disable)
EMA_FAST = 20                 # Fast Moving Average period
EMA_SLOW = 50                 # Slow Moving Average period (SL trailing reference)
TP_PCT = 25.0                 # Target Profit % from entry price
DEFAULT_SL_PCT = 5.0          # Initial Stop Loss % fallback


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

    # 1. Market Cap Filter (skip stocks below MIN_MARKET_CAP_CR)
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

    # 2. Simulate Trades with Trailing SL
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

    # 3. Output DataFrame for Table & Chart Inspection
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

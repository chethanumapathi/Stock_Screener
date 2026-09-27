import json
import os

new_code = '''"""
Strong buy - 9:15 High Volume from past 300 5 min candles
(Multi-Timeframe Scanner: 5-Min Volume Breakout + Weekly/Daily R2 + Market Cap)
===============================================================
Compatible with both SCREENER SANDBOX (screen) and BACKTEST SANDBOX (backtest).
This is a pure PASS/FAIL scanner (all conditions ANDed together), ported
from a Chartink-style screen.

RULES IMPLEMENTED (all must hold on the same 5-minute bar):

1. VOLUME BREAKOUT: current 5-min Volume > the highest 5-min Volume of
   the prior 300 five-minute bars (current bar excluded from that
   baseline).

2. 5-min Close > that week's Weekly Pivot R2 (R2 = Pivot + (High-Low),
   Pivot = (High+Low+Close)/3, computed from the PRIOR completed
   calendar week's OHLC, held constant across the current week).

3. 5-min Close > that day's Daily Pivot R2 (same formula, from the
   PRIOR completed calendar day's OHLC, held constant across the
   current day).

4. Market Cap > 5000 (Rs Cr).

5. 5-min Volume > 130,000 (an absolute liquidity floor, separate from
   the relative breakout in rule 1).

(Note: 15-min OBV condition removed per user request; can be restored if needed).
"""

import numpy as np
import pandas as pd

VOLUME_LOOKBACK_5MIN = 300      # bars, 5-min timeframe
MIN_VOLUME_5MIN = 130_000       # absolute floor, 5-min timeframe
MIN_MARKET_CAP_CR = 5000


def _compute_pivot_r2(ohlc: pd.DataFrame):
    """Pivot & R2 from the PRIOR completed period's OHLC, held constant
    across the current period's rows. `ohlc` must already be aggregated
    to the target period (e.g. one row per day, or per week)."""
    pivot = (ohlc['high'] + ohlc['low'] + ohlc['close']) / 3.0
    r2 = pivot + (ohlc['high'] - ohlc['low'])
    return pivot.shift(1), r2.shift(1)


def _map_period_value_to_base(base_index: pd.DatetimeIndex, period_index: pd.PeriodIndex, period_values: pd.Series) -> np.ndarray:
    """Maps a lower-frequency Series (indexed by Period) onto a higher-
    frequency (e.g. 5-min) index, by looking up each base row's period."""
    return period_values.reindex(period_index).to_numpy(dtype=float)


def backtest(df: pd.DataFrame) -> dict:
    df = df.copy()

    clean_cols = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow in ['open', 'high', 'low', 'close', 'volume', 'prev_close', 'date', 'market_cap_cr', 'symbol'] and clow not in clean_cols.values():
            clean_cols[c] = clow
    price_df = df[list(clean_cols.keys())].rename(columns=clean_cols)

    if 'date' in price_df.columns:
        price_df.index = pd.to_datetime(price_df['date'])
    else:
        price_df.index = pd.to_datetime(price_df.index)
    price_df = price_df.sort_index()

    for col in ('open', 'high', 'low', 'close', 'volume'):
        if col not in price_df.columns:
            raise ValueError(f"df is missing required column '{col}'")

    # ---- Market Cap gate (df column first, fallback to get_market_cap_cr) ----
    market_cap = None
    if 'market_cap_cr' in price_df.columns and pd.notna(price_df['market_cap_cr'].iloc[-1]):
        market_cap = float(price_df['market_cap_cr'].iloc[-1])
    else:
        symbol = None
        for c in ('symbol', 'Symbol'):
            if c in df.columns:
                symbol = df[c].iloc[-1]
                break
        try:
            market_cap = get_market_cap_cr(symbol, fetch_online=False) if symbol else None
        except Exception:
            market_cap = None

    if market_cap is None or market_cap <= MIN_MARKET_CAP_CR:
        return {
            "trades": [],
            "long_entry": pd.Series(False, index=df.index, name="long_entry"),
            "entries": pd.Series(False, index=df.index, name="entries"),
            "signal": pd.Series(False, index=df.index, name="signal"),
            "tp_pct": pd.Series(np.nan, index=df.index, name="tp_pct"),
            "sl_pct": pd.Series(np.nan, index=df.index, name="sl_pct"),
            "df": df
        }

    n = len(price_df)
    close5 = price_df['close'].to_numpy(dtype=float)
    volume5 = price_df['volume'].to_numpy(dtype=float)

    # ---- Rule 1: 5-min volume breakout (prior 300 bars, current excluded) ----
    vol_max_prior_300 = pd.Series(volume5, index=price_df.index).shift(1).rolling(
        VOLUME_LOOKBACK_5MIN, min_periods=VOLUME_LOOKBACK_5MIN
    ).max().to_numpy(dtype=float)
    cond_volume_breakout = ~np.isnan(vol_max_prior_300) & (volume5 > vol_max_prior_300)

    # ---- Rule 5: absolute 5-min volume floor ----
    cond_volume_floor = volume5 > MIN_VOLUME_5MIN

    # ---- Rules 2 & 3: Weekly / Daily R2, mapped onto 5-min rows ----
    day_period = price_df.index.to_period('D')
    week_period = price_df.index.to_period('W-FRI')

    daily_ohlc = price_df.groupby(day_period).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    weekly_ohlc = price_df.groupby(week_period).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))

    _, daily_r2 = _compute_pivot_r2(daily_ohlc)
    _, weekly_r2 = _compute_pivot_r2(weekly_ohlc)

    daily_r2_on_5min = _map_period_value_to_base(price_df.index, day_period, daily_r2)
    weekly_r2_on_5min = _map_period_value_to_base(price_df.index, week_period, weekly_r2)

    cond_above_daily_r2 = ~np.isnan(daily_r2_on_5min) & (close5 > daily_r2_on_5min)
    cond_above_weekly_r2 = ~np.isnan(weekly_r2_on_5min) & (close5 > weekly_r2_on_5min)

    signal = (
        cond_volume_breakout
        & cond_above_weekly_r2
        & cond_above_daily_r2
        & cond_volume_floor
    )

    # Once a stock comes up in the scanner in a day, ignore any subsequent scan triggers that day
    day_series = price_df.index.normalize()
    first_hit_mask = np.zeros(n, dtype=bool)
    seen_scan_days = set()
    for i in range(n):
        if signal[i]:
            d = day_series[i]
            if d not in seen_scan_days:
                seen_scan_days.add(d)
                first_hit_mask[i] = True
    signal = first_hit_mask

    date_strs = price_df.index.astype(str)

    out_df = price_df.copy()
    out_df['Vol_Max_Prior_300_5min'] = vol_max_prior_300
    out_df['Cond_Volume_Breakout'] = cond_volume_breakout
    out_df['Daily_R2'] = daily_r2_on_5min
    out_df['Weekly_R2'] = weekly_r2_on_5min
    out_df['Cond_Above_Daily_R2'] = cond_above_daily_r2
    out_df['Cond_Above_Weekly_R2'] = cond_above_weekly_r2
    out_df['Cond_Volume_Floor'] = cond_volume_floor
    out_df['Market_Cap_Cr'] = market_cap
    out_df['Scan_Pass'] = signal
    out_df['Date'] = date_strs

    signal_series = pd.Series(signal, index=df.index if len(df.index) == n else price_df.index, name="signal")

    return {
        "trades": [],
        "long_entry": signal_series.rename("long_entry"),
        "entries": signal_series.rename("entries"),
        "signal": signal_series,
        "tp_pct": pd.Series(np.nan, index=signal_series.index, name="tp_pct"),
        "sl_pct": pd.Series(np.nan, index=signal_series.index, name="sl_pct"),
        "df": out_df
    }

# Screener compatibility alias
screen = backtest
'''

strategies_path = r'c:\Stock_Screener\data\strategies.json'
with open(strategies_path, 'r', encoding='utf-8') as f:
    strategies = json.load(f)

updated = False
for s in strategies:
    if '9:15 High Volume' in s['name']:
        s['code'] = new_code
        print('Updated strategy:', s['name'])
        updated = True
        break

if updated:
    with open(strategies_path, 'w', encoding='utf-8') as f:
        json.dump(strategies, f, indent=4)
    print('Saved strategies.json successfully!')
else:
    print('Error: Strategy not found in strategies.json!')

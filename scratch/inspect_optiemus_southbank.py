import sys
sys.path.insert(0, r"c:\Stock_Screener")
import pandas as pd
import numpy as np
from app import get_ticker_data_duckdb, STRATEGIES_FILE, get_market_cap_cr
import json

with open(STRATEGIES_FILE, 'r', encoding='utf-8') as f:
    strategies = json.load(f)
strat = next(s for s in strategies if '9:15 High Volume' in s['name'])
code_str = strat['code']

targets = [
    ('OPTIEMUS', '2026-09-22 09:20'),
    ('SOUTHBANK', '2026-09-23 11:25')
]

VOLUME_LOOKBACK_5MIN = 300
MIN_VOLUME_5MIN = 130_000

def _compute_pivot_r2(ohlc: pd.DataFrame):
    pivot = (ohlc['high'] + ohlc['low'] + ohlc['close']) / 3.0
    r2 = pivot + (ohlc['high'] - ohlc['low'])
    return pivot.shift(1), r2.shift(1)

def _map_period_value_to_base(base_index: pd.DatetimeIndex, period_index: pd.PeriodIndex, period_values: pd.Series) -> np.ndarray:
    return period_values.reindex(period_index).to_numpy(dtype=float)

def check_stock(symbol, target_time):
    # Fetch with warm-up
    df = get_ticker_data_duckdb(symbol, timeframe='5m')
    if df.empty:
        print(f"Error: {symbol} has no data!")
        return

    clean_cols = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow in ['open', 'high', 'low', 'close', 'volume', 'prev_close', 'date'] and clow not in clean_cols.values():
            clean_cols[c] = clow
    price_df = df[list(clean_cols.keys())].rename(columns=clean_cols)
    price_df['date'] = price_df['date'].astype(str)
    price_df.index = pd.to_datetime(price_df['date'])
    price_df = price_df.sort_index()

    close5 = price_df['close'].to_numpy(dtype=float)
    volume5 = price_df['volume'].to_numpy(dtype=float)

    # 1. 5-min volume breakout
    vol_series = pd.Series(volume5, index=price_df.index)
    vol_max_prior_300 = vol_series.shift(1).rolling(
        VOLUME_LOOKBACK_5MIN, min_periods=VOLUME_LOOKBACK_5MIN
    ).max().to_numpy(dtype=float)
    cond_volume_breakout = ~np.isnan(vol_max_prior_300) & (volume5 > vol_max_prior_300)

    # 2. Volume floor
    cond_volume_floor = volume5 > MIN_VOLUME_5MIN

    # 3. Weekly & Daily R2
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

    raw_signal = (
        cond_volume_breakout
        & cond_above_weekly_r2
        & cond_above_daily_r2
        & cond_volume_floor
    )

    out = price_df.copy()
    out['vol_max_300'] = vol_max_prior_300
    out['c_vol_break'] = cond_volume_breakout
    out['c_vol_floor'] = cond_volume_floor
    out['daily_r2'] = daily_r2_on_5min
    out['c_daily_r2'] = cond_above_daily_r2
    out['weekly_r2'] = weekly_r2_on_5min
    out['c_weekly_r2'] = cond_above_weekly_r2
    out['signal'] = raw_signal

    mcap = get_market_cap_cr(symbol, fetch_online=False)

    print(f"\n{'='*75}")
    print(f"ANALYSIS: {symbol} at {target_time}")
    print(f"{'='*75}")
    print(f"Market Cap: {mcap} Cr (Gate > 5000 Cr: {mcap > 5000})")

    # Match target candle
    match = out[out['date'].str.startswith(target_time)]
    if match.empty:
        print(f"Candle {target_time} not found! Showing surrounding candles:")
        print(out[out['date'].str.startswith(target_time[:10])].head(10))
        return

    row = match.iloc[0]
    idx = match.index[0]

    print(f"Candle Details:")
    print(f"  Time:   {row['date']}")
    print(f"  Open:   {row['open']:.2f}")
    print(f"  High:   {row['high']:.2f}")
    print(f"  Low:    {row['low']:.2f}")
    print(f"  Close:  {row['close']:.2f}")
    print(f"  Volume: {int(row['volume']):,}")

    print(f"\nCondition Checks:")
    print(f"  1. Close vs Daily R2:")
    print(f"     Close = {row['close']:.2f} | Daily R2 = {row['daily_r2']:.2f} -> {row['c_daily_r2']}")
    print(f"  2. Close vs Weekly R2:")
    print(f"     Close = {row['close']:.2f} | Weekly R2 = {row['weekly_r2']:.2f} -> {row['c_weekly_r2']}")
    print(f"  3. 5-Min Volume Breakout (Prior 300 5m candles):")
    print(f"     Current Volume = {int(row['volume']):,} | Prior 300 Max = {int(row['vol_max_300']):,} -> {row['c_vol_break']}")
    print(f"  4. 5-Min Volume Floor (> 130,000):")
    print(f"     Current Volume = {int(row['volume']):,} -> {row['c_vol_floor']}")
    print(f"  5. Market Cap Gate (> 5000 Cr):")
    print(f"     Market Cap = {mcap} Cr -> {mcap > 5000}")

    print(f"\nOVERALL RESULT AT THIS CANDLE:")
    all_tech = row['c_daily_r2'] and row['c_weekly_r2'] and row['c_vol_break'] and row['c_vol_floor']
    print(f"  Technical Conditions Pass: {all_tech}")
    print(f"  Full Scanner Pass (with MCap): {all_tech and (mcap > 5000)}")

    # Top 5 volume in prior 300
    loc_pos = price_df.index.get_loc(idx)
    prior_300_df = price_df.iloc[max(0, loc_pos - 300) : loc_pos]
    top_vol = prior_300_df.sort_values('volume', ascending=False).head(5)
    print(f"\n  Top 5 highest volume candles in prior 300 5m bars:")
    for _, r in top_vol.iterrows():
        print(f"    Date: {r['date']} | Vol: {int(r['volume']):,} | Close: {r['close']:.2f}")

    # Also check if it triggered at ANY other candle on that day
    day_str = target_time[:10]
    day_matches = out[out['date'].str.startswith(day_str) & (out['signal'] == True)]
    print(f"\n  Any triggers on {day_str}? Total = {len(day_matches)}")
    for _, r in day_matches.iterrows():
        print(f"    MATCH at {r['date']} | Px: {r['close']} | Vol: {int(r['volume']):,}")

for sym, t in targets:
    check_stock(sym, t)

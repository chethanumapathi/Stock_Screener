import sys
sys.path.insert(0, r"c:\Stock_Screener")
import pandas as pd
import numpy as np
from app import get_ticker_data_duckdb, STRATEGIES_FILE, get_market_cap_cr

# Load strategy code
import json
with open(STRATEGIES_FILE, 'r', encoding='utf-8') as f:
    strategies = json.load(f)
strat = next(s for s in strategies if '9:15 High Volume' in s['name'])
code_str = strat['code']

# Target stocks and user times on 2026-09-25
targets = [
    ('SPARC', '2026-09-25 09:35'),
    ('ARTEMISMED', '2026-09-25 11:20'),
    ('LLOYDSENGG', '2026-09-25 11:35'),
    ('LLOYDSENT', '2026-09-25 11:35'),
    ('LCL', '2026-09-25 11:45'),
]

VOLUME_LOOKBACK_5MIN = 300
MIN_VOLUME_5MIN = 130_000
OBV_LOOKBACK_15MIN = 200

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

def _compute_pivot_r2(ohlc: pd.DataFrame):
    pivot = (ohlc['high'] + ohlc['low'] + ohlc['close']) / 3.0
    r2 = pivot + (ohlc['high'] - ohlc['low'])
    return pivot.shift(1), r2.shift(1)

def _map_period_value_to_base(base_index: pd.DatetimeIndex, period_index: pd.PeriodIndex, period_values: pd.Series) -> np.ndarray:
    return period_values.reindex(period_index).to_numpy(dtype=float)

def analyze_stock(symbol, target_time_str):
    df = get_ticker_data_duckdb(symbol, timeframe='5m')
    if df.empty:
        print(f"Error: No data for {symbol}")
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

    n = len(price_df)
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

    # 4. 15-min OBV breakout
    period_15min = price_df.index.floor('15min')
    ohlc_15min = price_df.groupby(period_15min).agg(close=('close', 'last'), volume=('volume', 'sum'))
    close15 = ohlc_15min['close'].to_numpy(dtype=float)
    volume15 = ohlc_15min['volume'].to_numpy(dtype=float)
    obv15 = compute_obv(close15, volume15)

    obv15_series = pd.Series(obv15, index=ohlc_15min.index)
    obv15_max_prior = obv15_series.shift(1).rolling(OBV_LOOKBACK_15MIN, min_periods=OBV_LOOKBACK_15MIN).max()
    cond_obv_15min = obv15_series >= obv15_max_prior

    cond_obv_15min_on_5min = cond_obv_15min.reindex(period_15min).to_numpy()
    cond_obv_15min_on_5min = np.where(pd.isna(cond_obv_15min_on_5min), False, cond_obv_15min_on_5min).astype(bool)

    raw_signal = (
        cond_volume_breakout
        & cond_above_weekly_r2
        & cond_above_daily_r2
        & cond_volume_floor
        & cond_obv_15min_on_5min
    )

    out = price_df.copy()
    out['vol_max_300'] = vol_max_prior_300
    out['c_vol_break'] = cond_volume_breakout
    out['c_vol_floor'] = cond_volume_floor
    out['daily_r2'] = daily_r2_on_5min
    out['c_daily_r2'] = cond_above_daily_r2
    out['weekly_r2'] = weekly_r2_on_5min
    out['c_weekly_r2'] = cond_above_weekly_r2
    out['obv15'] = pd.Series(obv15, index=ohlc_15min.index).reindex(period_15min).to_numpy()
    out['obv15_max_prior'] = obv15_max_prior.reindex(period_15min).to_numpy()
    out['c_obv'] = cond_obv_15min_on_5min
    out['signal'] = raw_signal

    mcap = get_market_cap_cr(symbol, fetch_online=False)

    print(f"\n================================================================================")
    print(f"ANALYSIS: {symbol} at {target_time_str}")
    print(f"================================================================================")
    print(f"Market Cap: {mcap} Cr (Gate > 5000 Cr: {mcap > 5000})")
    
    # Locate candle
    match = out[out['date'].str.startswith(target_time_str)]
    if match.empty:
        print(f"Candle at {target_time_str} not found! Showing surrounding candles:")
        surrounding = out[out['date'].str.startswith(target_time_str[:11])]
        print(surrounding[['date', 'open', 'high', 'low', 'close', 'volume']].head(10))
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
    prior_max = row['vol_max_300']
    print(f"     Current Volume = {int(row['volume']):,} | Prior 300 Max = {int(prior_max):,} -> {row['c_vol_break']}")
    print(f"  4. 5-Min Volume Floor (> 130,000):")
    print(f"     Current Volume = {int(row['volume']):,} -> {row['c_vol_floor']}")
    print(f"  5. 15-Min OBV Breakout (Prior 200 15m candles):")
    print(f"     Current OBV = {row['obv15']:,} | Prior 200 Max OBV = {row['obv15_max_prior']:,} -> {row['c_obv']}")
    print(f"  6. Market Cap Gate (> 5000 Cr):")
    print(f"     Market Cap = {mcap} Cr -> {mcap > 5000}")
    print(f"\nOVERALL RESULT AT THIS CANDLE:")
    all_tech = row['c_daily_r2'] and row['c_weekly_r2'] and row['c_vol_break'] and row['c_vol_floor'] and row['c_obv']
    print(f"  Technical Conditions Pass: {all_tech}")
    print(f"  Full Scanner Pass (with MCap): {all_tech and (mcap > 5000)}")

    # Check top volume candles in prior 300 bars to see why vol_max_300 is what it is
    loc_pos = price_df.index.get_loc(idx)
    prior_300_df = price_df.iloc[max(0, loc_pos - 300) : loc_pos]
    top_vol = prior_300_df.sort_values('volume', ascending=False).head(5)
    print(f"\n  Top 5 highest volume candles in the prior 300 5-min bars (lookback window):")
    for _, r in top_vol.iterrows():
        print(f"    Date: {r['date']} | Vol: {int(r['volume']):,} | Close: {r['close']:.2f}")

for sym, t in targets:
    analyze_stock(sym, t)

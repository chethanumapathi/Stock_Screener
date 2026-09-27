import sys
sys.path.insert(0, r"c:\Stock_Screener")
import pandas as pd
import numpy as np
from app import get_ticker_data_duckdb, get_market_cap_cr

VOLUME_LOOKBACK_5MIN = 300
MIN_VOLUME_5MIN = 130_000
OBV_LOOKBACK_15MIN = 200
OBV_EXCLUDE_CURRENT_BAR = True

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

def evaluate_stock_candles(symbol):
    df = get_ticker_data_duckdb(symbol, timeframe='5m')
    if df.empty:
        return None
    
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
    vol_max_prior_300 = pd.Series(volume5, index=price_df.index).shift(1).rolling(
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
    out['c_obv'] = cond_obv_15min_on_5min
    out['signal'] = raw_signal
    return out

stocks = ['TCI', 'SPARC', 'ARTEMISMED', 'LLOYDSENGG', 'LLOYDSENT', 'LCL']

for s in stocks:
    mcap = get_market_cap_cr(s, fetch_online=False)
    out = evaluate_stock_candles(s)
    print(f"\n{'='*70}\nSTOCK: {s} | System Market Cap: {mcap} Cr | Total 5m bars: {len(out)}\n{'='*70}")
    
    # Filter for 2026-09-21 through 2026-09-25
    week = out[out['date'].str.startswith(('2026-09-21', '2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25'))]
    all_triggers = week[week['signal'] == True]
    print(f"Technical Triggers This Week (Ignoring MCap): {len(all_triggers)}")
    for idx, r in all_triggers.iterrows():
        print(f"  >>> TRIGGER: Date={r['date']} | Px={r['close']} | Vol={int(r['volume'])} (300Max={int(r['vol_max_300'])}) | DailyR2={r['daily_r2']:.2f} | WeeklyR2={r['weekly_r2']:.2f}")

    print("\nDetailed Status on Friday 2026-09-25:")
    fri = week[week['date'].str.startswith('2026-09-25')]
    if fri.empty:
        print("  NO FRIDAY DATA!")
    else:
        # Check first 6 candles of Friday (09:15 to 09:40)
        for idx, r in fri.head(6).iterrows():
            t = r['date'][11:16]
            print(f"  [{t}] Px:{r['close']:7.2f} (DailyR2:{r['daily_r2']:7.2f} -> {r['c_daily_r2']}, WeeklyR2:{r['weekly_r2']:7.2f} -> {r['c_weekly_r2']})")
            print(f"         Vol:{int(r['volume']):8d} (Prior300Max:{int(r['vol_max_300']) if pd.notna(r['vol_max_300']) else 'NaN':8} -> {r['c_vol_break']}, Floor>130k -> {r['c_vol_floor']})")
            print(f"         OBV15mBreakout -> {r['c_obv']} | ALL CRITERIA -> {r['signal']}")

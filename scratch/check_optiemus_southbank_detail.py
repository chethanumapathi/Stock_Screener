import duckdb
import pandas as pd
import numpy as np

con = duckdb.connect()

def check_symbol(symbol, target_date, target_time):
    print(f"\n==================== {symbol} on {target_date} around {target_time} ====================")
    df = con.execute(f"SELECT * FROM 'data/minute/{symbol}.parquet' ORDER BY date").fetchdf()
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    # Resample to 5m
    df_5m = df.resample('5min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    
    # Prior 300 bars max volume
    df_5m['vol_max_300'] = df_5m['volume'].shift(1).rolling(300, min_periods=300).max()
    
    # Daily & Weekly R2
    day_period = df_5m.index.to_period('D')
    week_period = df_5m.index.to_period('W-FRI')
    daily_ohlc = df_5m.groupby(day_period).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    weekly_ohlc = df_5m.groupby(week_period).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    
    daily_p = (daily_ohlc['high'] + daily_ohlc['low'] + daily_ohlc['close']) / 3.0
    daily_r2 = (daily_p + (daily_ohlc['high'] - daily_ohlc['low'])).shift(1)
    
    weekly_p = (weekly_ohlc['high'] + weekly_ohlc['low'] + weekly_ohlc['close']) / 3.0
    weekly_r2 = (weekly_p + (weekly_ohlc['high'] - weekly_ohlc['low'])).shift(1)
    
    df_5m['daily_r2'] = daily_r2.reindex(day_period).to_numpy(dtype=float)
    df_5m['weekly_r2'] = weekly_r2.reindex(week_period).to_numpy(dtype=float)
    
    df_5m['pass_vol_breakout'] = df_5m['volume'] > df_5m['vol_max_300']
    df_5m['pass_vol_floor'] = df_5m['volume'] > 130000
    df_5m['pass_daily_r2'] = df_5m['close'] > df_5m['daily_r2']
    df_5m['pass_weekly_r2'] = df_5m['close'] > df_5m['weekly_r2']
    df_5m['all_pass'] = (
        df_5m['pass_vol_breakout'] &
        df_5m['pass_vol_floor'] &
        df_5m['pass_daily_r2'] &
        df_5m['pass_weekly_r2']
    )
    
    day_df = df_5m.loc[target_date]
    print(day_df[['open', 'high', 'low', 'close', 'volume', 'vol_max_300', 'daily_r2', 'weekly_r2', 'all_pass']].head(10))
    
    hits = day_df[day_df['all_pass']]
    print(f"\nAll Scan Hits for {symbol} on {target_date}: {len(hits)}")
    if not hits.empty:
        for idx, row in hits.iterrows():
            print(f"  Hit at {idx}: Close={row['close']}, Vol={int(row['volume'])}, Vol300Max={row['vol_max_300']}, DailyR2={row['daily_r2']:.2f}, WeeklyR2={row['weekly_r2']:.2f}")

check_symbol('OPTIEMUS', '2026-09-22', '09:20')
check_symbol('OPTIEMUS', '2026-09-23', '09:15')
check_symbol('SOUTHBANK', '2026-09-23', '11:25')

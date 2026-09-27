import sys
sys.path.append('.')
import pandas as pd
import numpy as np

df = pd.read_parquet('data/adjusted_daily/ACE.parquet')
if 'date' in df.columns:
    df.index = pd.to_datetime(df['date'])
elif not isinstance(df.index, pd.DatetimeIndex):
    df.index = pd.to_datetime(df.index)

# Monthly OHLC
m_ohlc = df.groupby(df.index.to_period('M')).agg(
    open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last')
)
m_pp = (m_ohlc['high'] + m_ohlc['low'] + m_ohlc['close']) / 3.0
m_r3_classical = m_ohlc['high'] + 2.0 * (m_pp - m_ohlc['low'])
m_r3_alt = m_pp + 2.0 * (m_ohlc['high'] - m_ohlc['low'])

print("Monthly OHLC and R3 for ACE in 2023:")
for m in ['2023-04', '2023-05', '2023-06', '2023-07', '2023-08']:
    p = pd.Period(m, freq='M')
    if p in m_ohlc.index:
        prev_p = p - 1
        r3_c = m_r3_classical.loc[prev_p] if prev_p in m_r3_classical.index else np.nan
        r3_a = m_r3_alt.loc[prev_p] if prev_p in m_r3_alt.index else np.nan
        print(f"Month {m}: O={m_ohlc.loc[p, 'open']:.2f}, H={m_ohlc.loc[p, 'high']:.2f}, L={m_ohlc.loc[p, 'low']:.2f}, C={m_ohlc.loc[p, 'close']:.2f} | Prior month R3 Classical={r3_c:.2f}, Alt={r3_a:.2f}")

print("\nDaily bars for ACE in June 2023:")
jun_2023 = df[(df.index >= '2023-06-01') & (df.index <= '2023-06-15')]
for idx, r in jun_2023.iterrows():
    print(f"  {idx.strftime('%Y-%m-%d')}: O={r['open']:.2f}, H={r['high']:.2f}, L={r['low']:.2f}, C={r['close']:.2f}")

print("\nDaily bars for ACE in July 2023:")
jul_2023 = df[(df.index >= '2023-07-01') & (df.index <= '2023-07-15')]
for idx, r in jul_2023.iterrows():
    print(f"  {idx.strftime('%Y-%m-%d')}: O={r['open']:.2f}, H={r['high']:.2f}, L={r['low']:.2f}, C={r['close']:.2f}")

# Also check 2024
print("\n--- Check 2024 ---")
for m in ['2024-04', '2024-05', '2024-06', '2024-07', '2024-08']:
    p = pd.Period(m, freq='M')
    if p in m_ohlc.index:
        prev_p = p - 1
        r3_c = m_r3_classical.loc[prev_p] if prev_p in m_r3_classical.index else np.nan
        r3_a = m_r3_alt.loc[prev_p] if prev_p in m_r3_alt.index else np.nan
        print(f"Month {m}: O={m_ohlc.loc[p, 'open']:.2f}, H={m_ohlc.loc[p, 'high']:.2f}, L={m_ohlc.loc[p, 'low']:.2f}, C={m_ohlc.loc[p, 'close']:.2f} | Prior month R3 Classical={r3_c:.2f}, Alt={r3_a:.2f}")

print("\nDaily bars for ACE in June 2024:")
jun_2024 = df[(df.index >= '2024-06-01') & (df.index <= '2024-06-15')]
for idx, r in jun_2024.iterrows():
    print(f"  {idx.strftime('%Y-%m-%d')}: O={r['open']:.2f}, H={r['high']:.2f}, L={r['low']:.2f}, C={r['close']:.2f}")

print("\nDaily bars for ACE in July 2024:")
jul_2024 = df[(df.index >= '2024-07-01') & (df.index <= '2024-07-15')]
for idx, r in jul_2024.iterrows():
    print(f"  {idx.strftime('%Y-%m-%d')}: O={r['open']:.2f}, H={r['high']:.2f}, L={r['low']:.2f}, C={r['close']:.2f}")

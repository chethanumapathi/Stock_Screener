import sys
sys.path.append('.')
import pandas as pd
from strategies.daily_monthly_r3_yearly_r2_breakout import backtest

df = pd.read_parquet('data/adjusted_daily/ACE.parquet')
res = backtest(df)
print("Trades for ACE:")
for t in res['trades']:
    print(t)

sig_df = res['df']
sigs = sig_df[sig_df['Signal']]
print(f"\nSignal candles for ACE ({len(sigs)} total):")
for idx, r in sigs.iterrows():
    d = r['date'] if 'date' in r else str(idx)
    c = r['close']
    h = r['high']
    mr3 = r['Monthly_R3']
    yr2 = r['Yearly_R2']
    print(f"  {d}: Close={c:.2f}, High={h:.2f}, Monthly_R3={mr3:.2f}, Yearly_R2={yr2:.2f}")

entries = sig_df[sig_df['Long_Entry']]
print(f"\nLong_Entry candles for ACE ({len(entries)} total):")
for idx, r in entries.iterrows():
    d = r['date'] if 'date' in r else str(idx)
    c = r['close']
    h = r['high']
    print(f"  {d}: Close={c:.2f}, High={h:.2f}")

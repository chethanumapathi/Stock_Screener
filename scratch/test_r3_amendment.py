import json
import numpy as np
import pandas as pd
from datetime import time as dtime

# Test the R3 logic on synthetic or real data
print("Testing pivot calculations...")
ohlc = pd.DataFrame({
    'high': [105.0, 110.0],
    'low': [95.0, 98.0],
    'close': [102.0, 108.0]
})

pivot = (ohlc['high'] + ohlc['low'] + ohlc['close']) / 3.0
r1 = 2.0 * pivot - ohlc['low']
r2 = pivot + (ohlc['high'] - ohlc['low'])
r3 = ohlc['high'] + 2.0 * (pivot - ohlc['low'])

print("Day 0 OHLC: H=105, L=95, C=102")
print(f"Pivot: {pivot.iloc[0]:.2f}")
print(f"R1: {r1.iloc[0]:.2f}")
print(f"R2: {r2.iloc[0]:.2f}")
print(f"R3: {r3.iloc[0]:.2f}")
print(f"R1 + Range: {(r1.iloc[0] + (ohlc['high'].iloc[0] - ohlc['low'].iloc[0])):.2f}")

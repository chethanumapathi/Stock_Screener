import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time as dtime

def test_simulation_logic():
    # Build 1-minute synthetic dataset for 5 days
    dates = []
    curr = pd.Timestamp('2024-01-01 09:15:00')
    while len(dates) < 375 * 4: # 4 days
        if curr.weekday() < 5:
            day_start = curr.replace(hour=9, minute=15)
            for b in range(375): # 375 1m bars per day
                dates.append(day_start + timedelta(minutes=b))
        curr += timedelta(days=1)
        
    df_1m = pd.DataFrame(index=pd.DatetimeIndex(dates))
    df_1m['open'] = 100.0
    df_1m['high'] = 100.5
    df_1m['low'] = 99.5
    df_1m['close'] = 100.0
    df_1m['volume'] = 1000.0
    
    # Days 0, 1: Baseline days at 100.0. Daily 260 EMA is ~100.0.
    # Day 2 (bars 750 to 1124): High=110, Low=90, Close=100. Daily Pivot = 100.0, Daily R3 = 130.0!
    # Daily 260 EMA will be ~150 if we set prior days higher, or let's set prior days close=150 so 260 EMA is 150.
    df_1m.iloc[0:750, df_1m.columns.get_loc('close')] = 150.0
    df_1m.iloc[0:750, df_1m.columns.get_loc('open')] = 150.0
    df_1m.iloc[0:750, df_1m.columns.get_loc('high')] = 155.0
    df_1m.iloc[0:750, df_1m.columns.get_loc('low')] = 145.0
    
    # Day 2 (bars 750 to 1124): Prior day drop to High=110, Low=90, Close=100 -> Daily R3 for Day 3 is 130.0.
    df_1m.iloc[750:1125, df_1m.columns.get_loc('high')] = 110.0
    df_1m.iloc[750:1125, df_1m.columns.get_loc('low')] = 90.0
    df_1m.iloc[750:1125, df_1m.columns.get_loc('close')] = 100.0
    df_1m.iloc[750:1125, df_1m.columns.get_loc('open')] = 100.0
    
    # Day 3 (bars 1125 onward):
    # From 09:15 to 09:40: rally up
    # 5m candle from 09:35 to 09:40 (bars 1145 to 1149):
    # Closes at 135.0 (> Daily R3 130.0, RSI > 85, Close < Daily 260 EMA ~140.0)
    for b in range(1125, 1150):
        val = 110.0 + (b - 1125) * 1.0
        df_1m.iloc[b, df_1m.columns.get_loc('open')] = val - 0.5
        df_1m.iloc[b, df_1m.columns.get_loc('close')] = val
        df_1m.iloc[b, df_1m.columns.get_loc('high')] = val + 0.5
        df_1m.iloc[b, df_1m.columns.get_loc('low')] = val - 1.0
        df_1m.iloc[b, df_1m.columns.get_loc('volume')] = 2000.0
        
    # At bar 1149 (09:39), 5m candle closes at 135.0. Daily R3 is 130.0.
    df_1m.iloc[1149, df_1m.columns.get_loc('close')] = 135.0
    df_1m.iloc[1149, df_1m.columns.get_loc('high')] = 136.0
    # Day high so far is 136.0
    
    # At 09:40 (bar 1150): The 5m candle is qualified!
    # But we do NOT short right away.
    # At 09:40-09:42: price stays high (135), above VWAP (~120).
    df_1m.iloc[1150:1153, df_1m.columns.get_loc('open')] = 135.0
    df_1m.iloc[1150:1153, df_1m.columns.get_loc('close')] = 134.5
    df_1m.iloc[1150:1153, df_1m.columns.get_loc('high')] = 135.5
    df_1m.iloc[1150:1153, df_1m.columns.get_loc('low')] = 134.0
    df_1m.iloc[1150:1153, df_1m.columns.get_loc('volume')] = 1000.0
    
    # At 09:43 (bar 1153): Price drops below VWAP!
    # VWAP is around 125.0. Candle 1153 closes at 124.0 (< VWAP).
    # Its High is 130.0, Low is 123.0, Close is 124.0.
    df_1m.iloc[1153, df_1m.columns.get_loc('open')] = 130.0
    df_1m.iloc[1153, df_1m.columns.get_loc('high')] = 130.0
    df_1m.iloc[1153, df_1m.columns.get_loc('low')] = 123.0
    df_1m.iloc[1153, df_1m.columns.get_loc('close')] = 124.0
    df_1m.iloc[1153, df_1m.columns.get_loc('volume')] = 5000.0
    # The low of this 1min candle is 123.0.
    
    # At 09:44 (bar 1154): Price breaks below 123.0!
    # Open = 123.5, Low = 120.0, Close = 121.0.
    # Entry short triggers at armed_low = 123.0!
    # TP = 2% = 123.0 * 0.98 = 120.54.
    # Since Low is 120.0 <= 120.54, TP is reached!
    df_1m.iloc[1154, df_1m.columns.get_loc('open')] = 123.5
    df_1m.iloc[1154, df_1m.columns.get_loc('high')] = 123.5
    df_1m.iloc[1154, df_1m.columns.get_loc('low')] = 120.0
    df_1m.iloc[1154, df_1m.columns.get_loc('close')] = 121.0
    df_1m.iloc[1154, df_1m.columns.get_loc('volume')] = 5000.0
    
    return df_1m

print("Synthetic test generator ready.")

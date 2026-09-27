import json
import pandas as pd
import numpy as np
from datetime import datetime

# Load sample_backtest_result.json
with open('scratch/sample_backtest_result.json', 'r') as f:
    data = json.load(f)

trades = data.get('trades', [])
overall_rep = data.get('overall_report', {})
print("Original overall_report metrics:")
print("  Max Drawdown:", overall_rep.get('max_drawdown'))
print("  Duration of Max Drawdown:", overall_rep.get('duration_of_max_drawdown'))
print("  Time Under Water %:", overall_rep.get('time_under_water_pct'))

# Let's inspect the trades and cum_equity
sorted_trades = sorted([t for t in trades if not t.get('is_open') and t.get('net_pnl') is not None], 
                       key=lambda x: pd.to_datetime(x.get('exit_date')))

cum_equity = 0.0
peak = 0.0
peak_date = None
mdd = 0.0
mdd_peak_dt = None
mdd_trough_dt = None

trade_records = []
for t in sorted_trades:
    cum_equity += t['net_pnl']
    dt = pd.to_datetime(t['exit_date'])
    if cum_equity >= peak:
        peak = cum_equity
        peak_date = dt
        dd = 0.0
    else:
        dd = cum_equity - peak
        if dd < mdd:
            mdd = dd
            mdd_peak_dt = peak_date
            mdd_trough_dt = dt
    trade_records.append({'date': dt, 'cum_equity': cum_equity, 'peak': peak, 'dd': dd})

print(f"\nTrade loop MDD: {mdd:.2f}")
print(f"MDD Peak Date: {mdd_peak_dt}, MDD Trough Date: {mdd_trough_dt}")
if mdd_peak_dt and mdd_trough_dt:
    print(f"Peak to Trough days: {(mdd_trough_dt - mdd_peak_dt).days}")

# Find when cum_equity recovered back to mdd_peak level
recovery_dt = None
for r in trade_records:
    if r['date'] > mdd_trough_dt and r['cum_equity'] >= trade_records[trade_records.index(next(x for x in trade_records if x['date'] == mdd_peak_dt))]['cum_equity']:
        recovery_dt = r['date']
        break

print(f"Recovery Date for this MDD: {recovery_dt}")
if recovery_dt and mdd_peak_dt:
    print(f"Total Peak-to-Recovery days for MDD: {(recovery_dt - mdd_peak_dt).days}")
else:
    print("This MDD never recovered before end of data!")

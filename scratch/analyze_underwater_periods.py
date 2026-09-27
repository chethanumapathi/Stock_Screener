import json
import pandas as pd
import numpy as np

with open('scratch/sample_backtest_result.json', 'r') as f:
    data = json.load(f)

# Reconstruct daily equity from trades
trades = [t for t in data.get('trades', []) if not t.get('is_open') and t.get('net_pnl') is not None]
trades = sorted(trades, key=lambda x: pd.to_datetime(x.get('exit_date')))

base_capital = data['overall_report']['peak_capital_deployed']
d_in_list = [pd.to_datetime(t['entry_date']) for t in trades if t.get('entry_date')]
d_out_list = [pd.to_datetime(t['exit_date']) for t in trades if t.get('exit_date')]
min_date = min(d_in_list)
max_date = max(d_out_list)

cur_d = min_date
t_ptr = 0
running_eq = base_capital
daily_dates = []
daily_equity = []

while cur_d <= max_date:
    while t_ptr < len(trades):
        ex_dt = pd.to_datetime(trades[t_ptr]['exit_date'])
        if ex_dt <= cur_d:
            running_eq += trades[t_ptr]['net_pnl']
            t_ptr += 1
        else:
            break
    daily_dates.append(cur_d)
    daily_equity.append(running_eq)
    cur_d += pd.Timedelta(days=1)

eq = np.array(daily_equity)
peaks = np.maximum.accumulate(eq)
dds = eq - peaks

# Identify all drawdown periods
# An underwater period starts when eq < peak (day i) where day i-1 was at peak,
# and ends when eq reaches peak again (or end of data).
underwater_periods = []
in_dd = False
start_idx = 0
trough_idx = 0
max_depth = 0.0

for i in range(len(eq)):
    if eq[i] < peaks[i]:
        if not in_dd:
            in_dd = True
            start_idx = i - 1  # Peak date
            trough_idx = i
            max_depth = dds[i]
        else:
            if dds[i] < max_depth:
                max_depth = dds[i]
                trough_idx = i
    else:
        if in_dd:
            in_dd = False
            recovery_idx = i
            p_date = daily_dates[start_idx]
            t_date = daily_dates[trough_idx]
            r_date = daily_dates[recovery_idx]
            underwater_periods.append({
                'peak_date': p_date,
                'trough_date': t_date,
                'recovery_date': r_date,
                'depth': max_depth,
                'contraction_days': (t_date - p_date).days,
                'recovery_days': (r_date - t_date).days,
                'total_duration_days': (r_date - p_date).days,
                'is_recovered': True
            })

if in_dd:
    p_date = daily_dates[start_idx]
    t_date = daily_dates[trough_idx]
    r_date = daily_dates[-1]
    underwater_periods.append({
        'peak_date': p_date,
        'trough_date': t_date,
        'recovery_date': r_date,
        'depth': max_depth,
        'contraction_days': (t_date - p_date).days,
        'recovery_days': (r_date - t_date).days,
        'total_duration_days': (r_date - p_date).days,
        'is_recovered': False
    })

print(f"Total underwater periods found: {len(underwater_periods)}")
# Sort by depth
by_depth = sorted(underwater_periods, key=lambda x: x['depth'])
print("\nTop 3 Deepest Drawdowns:")
for idx, p in enumerate(by_depth[:3], 1):
    rec_str = p['recovery_date'].strftime('%d-%b-%Y') if p['is_recovered'] else f"{p['recovery_date'].strftime('%d-%b-%Y')} (Ongoing)"
    print(f" {idx}. Depth: Rs {p['depth']:,.2f} | Peak: {p['peak_date'].strftime('%d-%b-%Y')} -> Trough: {p['trough_date'].strftime('%d-%b-%Y')} ({p['contraction_days']}d) -> Recovery: {rec_str} ({p['recovery_days']}d) | Total Duration: {p['total_duration_days']} days")

# Sort by duration
by_duration = sorted(underwater_periods, key=lambda x: x['total_duration_days'], reverse=True)
print("\nTop 3 Longest Drawdowns:")
for idx, p in enumerate(by_duration[:3], 1):
    rec_str = p['recovery_date'].strftime('%d-%b-%Y') if p['is_recovered'] else f"{p['recovery_date'].strftime('%d-%b-%Y')} (Ongoing)"
    print(f" {idx}. Duration: {p['total_duration_days']} days | Depth: Rs {p['depth']:,.2f} | Peak: {p['peak_date'].strftime('%d-%b-%Y')} -> Trough: {p['trough_date'].strftime('%d-%b-%Y')} -> Recovery: {rec_str}")

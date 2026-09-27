import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

with open('scratch/sample_backtest_result.json', 'r') as f:
    data = json.load(f)

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
daily_dates_list = []
daily_equity_list = []

while cur_d <= max_date:
    while t_ptr < len(trades):
        ex_dt = pd.to_datetime(trades[t_ptr]['exit_date'])
        if ex_dt <= cur_d:
            running_eq += trades[t_ptr]['net_pnl']
            t_ptr += 1
        else:
            break
    daily_dates_list.append(cur_d.strftime('%Y-%m-%d'))
    daily_equity_list.append(round(running_eq, 2))
    cur_d += timedelta(days=1)

def compute_detailed_drawdowns(daily_dates_list, daily_equity_list, overall_max_dd=None):
    if not daily_equity_list or len(daily_equity_list) < 2:
        return {
            "mdd_total_days": 0,
            "mdd_contraction_days": 0,
            "mdd_recovery_days": 0,
            "mdd_peak_str": "-",
            "mdd_trough_str": "-",
            "mdd_recovery_str": "-",
            "mdd_duration_str": "-",
            "longest_dd_days": 0,
            "longest_dd_str": "-",
            "all_underwater_periods": []
        }

    eq = np.array(daily_equity_list, dtype=float)
    peak = np.maximum.accumulate(eq)
    dds = eq - peak
    dates = [datetime.strptime(d, '%Y-%m-%d') for d in daily_dates_list]
    n = len(eq)

    underwater_periods = []
    in_dd = False
    p_idx = 0
    t_idx = 0
    min_dd = 0.0

    for i in range(n):
        if eq[i] < peak[i]:
            if not in_dd:
                in_dd = True
                p_idx = max(0, i - 1)
                t_idx = i
                min_dd = dds[i]
            else:
                if dds[i] < min_dd:
                    min_dd = dds[i]
                    t_idx = i
        else:
            if in_dd:
                in_dd = False
                rec_idx = i
                p_dt = dates[p_idx]
                t_dt = dates[t_idx]
                r_dt = dates[rec_idx]
                underwater_periods.append({
                    "peak_date": p_dt,
                    "trough_date": t_dt,
                    "recovery_date": r_dt,
                    "depth": min_dd,
                    "contraction_days": max(1, (t_dt - p_dt).days),
                    "recovery_days": max(0, (r_dt - t_dt).days),
                    "total_days": max(1, (r_dt - p_dt).days),
                    "is_recovered": True
                })

    if in_dd:
        p_dt = dates[p_idx]
        t_dt = dates[t_idx]
        r_dt = dates[-1]
        underwater_periods.append({
            "peak_date": p_dt,
            "trough_date": t_dt,
            "recovery_date": r_dt,
            "depth": min_dd,
            "contraction_days": max(1, (t_dt - p_dt).days),
            "recovery_days": max(0, (r_dt - t_dt).days),
            "total_days": max(1, (r_dt - p_dt).days),
            "is_recovered": False
        })

    if not underwater_periods:
        return {
            "mdd_total_days": 0,
            "mdd_contraction_days": 0,
            "mdd_recovery_days": 0,
            "mdd_peak_str": "-",
            "mdd_trough_str": "-",
            "mdd_recovery_str": "-",
            "mdd_duration_str": "-",
            "longest_dd_days": 0,
            "longest_dd_str": "-",
            "all_underwater_periods": []
        }

    # Find the deepest drawdown period (matching overall_max_dd)
    mdd_period = min(underwater_periods, key=lambda x: x["depth"])
    p_str = mdd_period["peak_date"].strftime('%d-%b-%Y')
    t_str = mdd_period["trough_date"].strftime('%d-%b-%Y')
    r_str = mdd_period["recovery_date"].strftime('%d-%b-%Y')
    if not mdd_period["is_recovered"]:
        r_str += " (Ongoing)"

    # Formatted duration string showing both total recovery and breakdown
    # e.g.: "392d [02-Oct-2024 to 29-Oct-2025] (Fall: 149d | Rec: 243d)"
    tot_days = mdd_period["total_days"]
    c_days = mdd_period["contraction_days"]
    r_days = mdd_period["recovery_days"]
    mdd_dur_str = f"{tot_days}d [{p_str} to {r_str}] (Fall: {c_days}d, Rec: {r_days}d)"

    # Longest underwater period across all drawdowns
    longest_period = max(underwater_periods, key=lambda x: x["total_days"])
    lp_p_str = longest_period["peak_date"].strftime('%d-%b-%Y')
    lp_r_str = longest_period["recovery_date"].strftime('%d-%b-%Y')
    if not longest_period["is_recovered"]:
        lp_r_str += " (Ongoing)"
    longest_dur_str = f"{longest_period['total_days']}d [{lp_p_str} to {lp_r_str}]"

    return {
        "mdd_total_days": tot_days,
        "mdd_contraction_days": c_days,
        "mdd_recovery_days": r_days,
        "mdd_peak_str": p_str,
        "mdd_trough_str": t_str,
        "mdd_recovery_str": r_str,
        "mdd_duration_str": mdd_dur_str,
        "longest_dd_days": longest_period["total_days"],
        "longest_dd_str": longest_dur_str,
        "all_underwater_periods": underwater_periods
    }

res = compute_detailed_drawdowns(daily_dates_list, daily_equity_list)
print("Computed Results:")
print("MDD Duration String:", res["mdd_duration_str"])
print("Longest Underwater Period:", res["longest_dd_str"])

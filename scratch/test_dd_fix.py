import json
from datetime import datetime

# Let's inspect the logic
# Suppose we have trades in a year
def compute_year_dd(trades):
    # trades sorted by exit_date
    yr_cum = 0.0
    yr_running_peak = 0.0
    # If no peak yet, the starting point is 0 at the start of the year or entry of first trade
    first_dt = trades[0].get('entry_date') or trades[0].get('exit_date')
    yr_running_peak_dt = first_dt
    
    yr_max_dd = 0.0
    yr_mdd_peak_dt = first_dt
    yr_mdd_trough_dt = first_dt
    
    for tr in trades:
        yr_cum += tr['net_pnl']
        if yr_cum >= yr_running_peak:
            yr_running_peak = yr_cum
            yr_running_peak_dt = tr['exit_date']
        else:
            curr_dd = yr_cum - yr_running_peak
            if curr_dd < yr_max_dd:
                yr_max_dd = curr_dd
                yr_mdd_trough_dt = tr['exit_date']
                yr_mdd_peak_dt = yr_running_peak_dt
                
    return yr_max_dd, yr_mdd_peak_dt, yr_mdd_trough_dt

print("DD fix logic defined.")

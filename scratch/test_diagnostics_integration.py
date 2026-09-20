import sys
sys.path.insert(0, '.')
import json
import time
from app import run_backtest_simulation

from app import compute_backtest_analytics

# Let's create realistic sample trades including the exact 2023, 2024, 2025 trades
sample_trades = [
    {"symbol": "VESUVIUS", "qty": 100, "entry_date": "2023-05-26", "entry_price": 243.28, "exit_date": "2023-09-22", "exit_price": 230.0, "net_pnl": -14020.48, "pnl_pct": -5.46, "mae_pct": -6.0, "mfe_pct": 10.0},
    {"symbol": "TRENT", "qty": 100, "entry_date": "2023-10-10", "entry_price": 1000.0, "exit_date": "2023-11-17", "exit_price": 1500.0, "net_pnl": 655715.29, "pnl_pct": 50.0, "mae_pct": -2.0, "mfe_pct": 55.0},
    {"symbol": "KAYNES", "qty": 100, "entry_date": "2024-01-15", "entry_price": 2000.0, "exit_date": "2024-05-17", "exit_price": 1800.0, "net_pnl": -107156.81, "pnl_pct": -10.0, "mae_pct": -12.0, "mfe_pct": 5.0},
    {"symbol": "DIXON", "qty": 100, "entry_date": "2024-06-01", "entry_price": 3000.0, "exit_date": "2024-12-27", "exit_price": 6000.0, "net_pnl": 4462465.43, "pnl_pct": 100.0, "mae_pct": -4.0, "mfe_pct": 100.0},
    {"symbol": "BEL", "qty": 100, "entry_date": "2025-01-03", "entry_price": 150.0, "exit_date": "2025-01-20", "exit_price": 140.0, "net_pnl": -12691.64, "pnl_pct": -6.67, "mae_pct": -8.0, "mfe_pct": 2.0},
    {"symbol": "HAL", "qty": 100, "entry_date": "2025-02-10", "entry_price": 2500.0, "exit_date": "2025-08-15", "exit_price": 5000.0, "net_pnl": 1263942.54, "pnl_pct": 100.0, "mae_pct": -3.0, "mfe_pct": 100.0},
]

t0 = time.time()
res = compute_backtest_analytics(sample_trades)
t1 = time.time()
print(f"Analytics done in {t1-t0:.4f}s")

print("\n--- YEAR-WISE DRAWDOWN DATES CHECK ---")
all_dates_ordered = True
for r in res.get('year_wise_returns', []):
    days_str = r.get('days_for_mdd')
    print(f"Year {r.get('year')}: Total={r.get('total')} MDD={r.get('max_drawdown')} Days={days_str} CAGR={r.get('cagr')}%")
    if '[' in days_str and 'to' in days_str:
        parts = days_str.split('[')[1].split(']')[0].split(' to ')
        d1 = parts[0].strip()
        d2 = parts[1].strip()
        from datetime import datetime
        dt1 = datetime.strptime(d1, '%d-%b-%Y')
        dt2 = datetime.strptime(d2, '%d-%b-%Y')
        if dt1 > dt2:
            print(f"  [ERROR] {d1} > {d2} in year {r.get('year')}")
            all_dates_ordered = False

if all_dates_ordered:
    print("SUCCESS: All year-wise drawdown dates are chronologically sorted (start <= end)!")

print("\n--- OVERALL REPORT NEW METRICS ---")
rep = res.get('overall_report', {})
print("Recovery Factor:", rep.get('recovery_factor'))
print("Ulcer Index:", rep.get('ulcer_index'))
print("Time Under Water %:", rep.get('time_under_water_pct'))

print("\n--- DIAGNOSTICS SUITE KEYS CHECK ---")
diag = res.get('diagnostics', {})
print("Diagnostics keys:", list(diag.keys()))
bm = diag.get('benchmark_comparison', {})
print("Benchmark Strategy CAGR vs Nifty CAGR:", bm.get('strategy_cagr'), "% vs", bm.get('nifty_cagr'), "%")
print("Alpha:", bm.get('alpha'), "Beta:", bm.get('beta'), "Correlation:", bm.get('correlation'))
mc = diag.get('monte_carlo', {})
print("Monte Carlo Median MDD:", mc.get('stats', {}).get('median_mdd'), "P95 MDD:", mc.get('stats', {}).get('p95_worst_case_mdd'))
oos = diag.get('out_of_sample_split', {})
print("OOS Degradation Ratio:", oos.get('degradation_ratio'), "Status:", oos.get('status'))
reg = diag.get('regime_split', {})
print("Regimes:", [r['regime'] for r in reg.get('regimes', [])])
sec = diag.get('sector_mcap', {})
print("Top sectors count:", len(sec.get('sectors', [])))
pos = diag.get('position_sizing', {})
print("Sizing models:", list(pos.get('models', {}).keys()))

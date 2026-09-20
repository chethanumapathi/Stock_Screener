import urllib.request
import json
import os

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    strats = json.load(f)

target = next(s for s in strats if 'Weekly Yearly-R1' in s['name'])
payload = json.dumps({
    'code': target['code'],
    'segment': 'nifty50',
    'timeframe': '1d',
    'start_date': '2023-01-01',
    'end_date': '2026-09-20'
}).encode('utf-8')

req = urllib.request.Request('http://127.0.0.1:8000/api/backtest', data=payload, headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req, timeout=120)
data = json.loads(res.read().decode())

print('Status:', data.get('status'))
rep = data.get('overall_report', {})
print('Overall Profit:', rep.get('overall_profit'))
print('Recovery Factor:', rep.get('recovery_factor'), 'Ulcer Index:', rep.get('ulcer_index'), 'Time Under Water:', rep.get('time_under_water_pct'))

print('\nYear-wise Returns:')
for r in data.get('year_wise_returns', []):
    print(f"  Year {r.get('year')}: DD Window={r.get('max_drawdown_dates')} | CAGR={r.get('cagr_pct')}% | Trades={r.get('trades')}")

diag = data.get('diagnostics', {})
print('\nDiagnostics payload keys:', list(diag.keys()))
if 'benchmark_comparison' in diag:
    bc = diag['benchmark_comparison']
    print(f"Benchmark: Strat CAGR={bc.get('strat_cagr')}%, Nifty CAGR={bc.get('nifty_cagr')}%, Alpha={bc.get('alpha')}%, Beta={bc.get('beta')}")
if 'out_of_sample_split' in diag:
    oos = diag['out_of_sample_split']
    print(f"OOS Split: Degradation={oos.get('degradation_ratio')}, IS={oos.get('is_trades_count')}, OOS={oos.get('oos_trades_count')}")
if 'monte_carlo' in diag:
    mc = diag['monte_carlo']
    print(f"Monte Carlo KPIs: {mc.get('kpis')}")
if 'parameter_sensitivity' in diag:
    ps = diag['parameter_sensitivity']
    print(f"Parameter Sensitivity TP Options: {ps.get('tp_options')}")
if 'regime_split' in diag:
    rs = diag['regime_split']
    print(f"Regimes: {[r['regime'] for r in rs.get('regimes', [])]}")
if 'pnl_distribution' in diag:
    pd = diag['pnl_distribution']
    print(f"PnL Dist: Skew={pd.get('skewness')}, Kurt={pd.get('kurtosis')}")
if 'sector_mcap' in diag:
    sm = diag['sector_mcap']
    print(f"Mcap Tiers: {[m['tier'] for m in sm.get('mcap_tiers', [])]}")
if 'concurrent_timeline' in diag:
    ct = diag['concurrent_timeline']
    print(f"Timeline: Peak Concurrent={ct.get('peak_concurrent')}, Avg Util={ct.get('avg_utilization_pct')}%")
if 'rolling_metrics' in diag:
    rm = diag['rolling_metrics']
    print(f"Rolling Metrics: {len(rm.get('dates', []))} data points")
if 'position_sizing' in diag:
    pos = diag['position_sizing']
    print(f"Position Sizing Models: {list(pos.get('models', {}).keys())}")

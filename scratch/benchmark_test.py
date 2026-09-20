import sys
sys.path.insert(0, '.')
import json
import time
from app import run_backtest_simulation

s = json.load(open('data/backtest_strategies.json', encoding='utf-8'))[27]
print('Testing backtest for:', s['name'])
t0 = time.time()
res = run_backtest_simulation(s['code'], segment='all')
t1 = time.time()
print(f"Done in {t1-t0:.2f}s, trades: {len(res.get('trades', []))}")
rep = res.get('overall_report', {})
print(f"Profit: {rep.get('overall_profit')}, Trades: {rep.get('no_of_trades')}, Win: {rep.get('win_trades')}, Loss: {rep.get('loss_trades')}, CAGR: {rep.get('cagr_pct')}%")
for row in res.get('year_wise_returns', []):
    print(f"Year {row.get('year')}: Total={row.get('total')} MDD={row.get('max_drawdown')} Days={row.get('days_for_mdd')}")

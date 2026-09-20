import sys
sys.path.insert(0, '.')
from app import compute_backtest_analytics

mock_trades = [
    {'entry_date': '2023-01-10', 'exit_date': '2023-02-15', 'entry_price': 100, 'exit_price': 120, 'qty': 100, 'net_pnl': 20000, 'mae_pct': 2.5, 'mfe_pct': 22.0, 'symbol': 'INFY'},
    {'entry_date': '2023-03-05', 'exit_date': '2023-04-10', 'entry_price': 200, 'exit_price': 180, 'qty': 100, 'net_pnl': -10000, 'mae_pct': 12.0, 'mfe_pct': 2.0, 'symbol': 'TCS'},
    {'entry_date': '2024-01-15', 'exit_date': '2024-03-20', 'entry_price': 150, 'exit_price': 200, 'qty': 100, 'net_pnl': 35000, 'mae_pct': 3.0, 'mfe_pct': 38.0, 'symbol': 'RELIANCE'},
]

res = compute_backtest_analytics(mock_trades, capital_per_trade=100000)
rep = res['overall_report']
print('=== OVERALL REPORT TEST ===')
print('Win trades:', rep.get('win_trades'), 'Win %:', rep.get('win_pct'))
print('Loss trades:', rep.get('loss_trades'), 'Loss %:', rep.get('loss_pct'))
print('Profit Factor:', rep.get('profit_factor'))
print('Peak Capital:', rep.get('peak_capital_deployed'))
print('Calmar Ratio:', rep.get('calmar_ratio'))

print('=== YEAR-WISE RETURNS TEST ===')
for row in res.get('year_wise_returns', []):
    print(f"Year {row['year']}: Total={row['total']}, MaxDD={row['max_drawdown']}, CAGR={row['cagr']}%")

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app
import json

code = next(s['code'] for s in app.load_strategies_from_file() if 'Bullish Trend' in s['name'])
code_fixed = code.replace(
    '"signal": pd.Series(signal, index=hourly.index, name="signal"),',
    '"signal": pd.Series(entries, index=hourly.index, name="signal"),\n        "in_trade": pd.Series(signal, index=hourly.index, name="in_trade"),'
)

res = app.run_screener_logic(code_fixed, 'nifty50', timeframe='1h')
print('Status:', res['status'])
print('Total matches:', res['total_matches'])
print('Dates with matches:', res['dates_with_matches'])
print('Recent triggers:')
for m in res['flat_matches'][:15]:
    print(f"{m['Date']} | {m['Symbol']:<12} | Close: {m['Close']:>8.2f} | Pct: {m['Pct_Change']:>5.2f}% | Stage: {m['custom_data'].get('stage')}")

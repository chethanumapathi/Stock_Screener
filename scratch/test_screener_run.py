import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app
import json

code = next(s['code'] for s in app.load_strategies_from_file() if 'Bullish Trend' in s['name'])

res = app.run_screener_logic(code, 'nifty50', timeframe='1h')
print('Status:', res['status'])
print('Total matches:', res['total_matches'])
print('Dates with matches:', res['dates_with_matches'])
print('Recent triggers:')
for m in res['flat_matches'][:15]:
    custom_keys = list(m['custom_data'].keys())
    print(f"{m['Date']} | {m['Symbol']:<12} | Close: {m['Close']:>8.2f} | Pct: {m['Pct_Change']:>5.2f}% | R2 Cross: {m['custom_data'].get('R2_Cross_Date')} | Keys in custom_data: {custom_keys}")

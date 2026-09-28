import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import app
import pandas as pd

# Load strategy
strategies = app.load_strategies_from_file()
strat = [s for s in strategies if 'Strong buy' in s['name']][0]
code = strat['code']

print(f"Strategy: {strat['name']}")

# Let's test on segment 'nifty50' for today '2026-09-28'
result = app.run_screener_logic(
    code_str=code,
    segment='nifty50',
    timeframe='5m',
    start_date='2026-09-28',
    end_date='2026-09-28',
    min_market_cap_cr=0
)

print("Status:", result.get('status'))
print("Total matches:", result.get('total_matches'))
print("Flat matches count:", len(result.get('flat_matches', [])))
for m in result.get('flat_matches', [])[:5]:
    print("Match:", m['Symbol'], m['Date'], m['Close'], m['Volume'])

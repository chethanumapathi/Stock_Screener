import sys
import os
sys.path.insert(0, os.path.abspath('.'))
import json
import pandas as pd
from app import run_screener_logic, get_market_cap_cr

# Load strategy code
with open('data/strategies.json', 'r', encoding='utf-8') as f:
    strats = json.load(f)

strat = next(s for s in strats if '9:15 High Volume' in s['name'])
code_str = strat['code']

test_symbols = ['SPARC', 'TCI', 'ARTEMISMED', 'LLOYDSENGG', 'LLOYDSENT', 'LCL']

print("=== Market Caps of Test Stocks ===")
for s in test_symbols:
    print(f"  {s}: {get_market_cap_cr(s, fetch_online=False):.2f} Cr")

def print_results(label, res):
    matches = res.get('flat_matches', [])
    print(f"\n=== {label}: {len(matches)} matches ===")
    for m in matches:
        s = m.get('Symbol') or m.get('symbol')
        d = m.get('Date') or m.get('date')
        c = m.get('Close') or m.get('close')
        v = m.get('Volume') or m.get('volume')
        mc = m.get('Market_Cap_Cr') or m.get('market_cap_cr')
        print(f"  {s:12} @ {d} | Close: {c:8.2f} | Vol: {int(v):8d} | Mcap: {mc:.2f} Cr")

# Test 1: min_market_cap_cr = 2000 Cr (All 6 should pass)
res_2000 = run_screener_logic(
    code_str=code_str,
    segment='watchlist',
    timeframe='5m',
    watchlist_symbols=test_symbols,
    start_date='2026-09-25',
    end_date='2026-09-25',
    min_market_cap_cr=2000.0
)
print_results("Testing min_market_cap_cr = 2000 Cr", res_2000)

# Test 2: min_market_cap_cr = 6000 Cr (SPARC 6040, TCI 6362, LLOYDSENGG 12442, LLOYDSENT 10302 should pass; ARTEMISMED 5181, LCL 5509 should be excluded)
res_6000 = run_screener_logic(
    code_str=code_str,
    segment='watchlist',
    timeframe='5m',
    watchlist_symbols=test_symbols,
    start_date='2026-09-25',
    end_date='2026-09-25',
    min_market_cap_cr=6000.0
)
print_results("Testing min_market_cap_cr = 6000 Cr", res_6000)

# Test 3: min_market_cap_cr = 11000 Cr (Only LLOYDSENGG 12442 should pass)
res_11000 = run_screener_logic(
    code_str=code_str,
    segment='watchlist',
    timeframe='5m',
    watchlist_symbols=test_symbols,
    start_date='2026-09-25',
    end_date='2026-09-25',
    min_market_cap_cr=11000.0
)
print_results("Testing min_market_cap_cr = 11000 Cr", res_11000)

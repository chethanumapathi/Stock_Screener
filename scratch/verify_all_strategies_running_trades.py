import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))
import json
from app import run_backtest_simulation, compute_backtest_analytics

print("==================================================================")
print("TEST 1: Best Swing Trade Strategy Verification")
print("==================================================================")

with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_strats = json.load(f)

best_swing = next((s for s in bt_strats if 'Best Swing' in s.get('name', '')), None)
assert best_swing is not None, "Best Swing Trade not found in backtest_strategies.json!"

# Run on symbols with known running trades
test_symbols = ['ADANIPOWER', 'SBC', 'THANGAMAYL', 'KARURVYSYA', 'QUESS', 'DOLPHIN', 'RAYMOND', 'RELIANCE', 'TCS']
res = run_backtest_simulation(
    best_swing['code'],
    timeframe='1d',
    segment='watchlist',
    watchlist_symbols=test_symbols,
    capital_per_trade=100000.0,
    slippage_pct=0.5,
    include_brokerage=True,
    include_taxes=True
)

trades = res.get('trades', [])
overall = res.get('overall_report', {})

print(f"Total trades: {len(trades)}")
print(f"Closed trades: {overall.get('no_of_trades')}")
print(f"Still running trades count: {overall.get('still_running_trades')}")
print(f"Still running MTM: INR {overall.get('still_running_mtm')}")
print(f"Still running string: {overall.get('still_running_str')}")

running_trades = [t for t in trades if t.get('is_open') or t.get('exit_reason') == 'Still Running']
assert len(running_trades) == overall.get('still_running_trades'), "Count mismatch between running trades and overall report!"

print(f"\nInspecting {len(running_trades)} Running Trades:")
for t in running_trades:
    print(f"  [{t['symbol']}] Entry: {t['entry_date']} | Exit: {t['exit_date']} | Reason: {t['exit_reason']} | Duration: {t['duration']} | MTM: INR {t['mtm_pnl']:+,.2f} ({t['mtm_pct']}%)")
    assert t['exit_date'] == "-", f"Expected exit_date '-' but got {t['exit_date']}"
    assert t['exit_reason'] == "Still Running", f"Expected exit_reason 'Still Running' but got {t['exit_reason']}"
    assert t['is_open'] is True, f"Expected is_open True but got {t['is_open']}"
    assert 'd (Running)' in t['duration'] or t['duration'] == 'Running', f"Invalid duration format: {t['duration']}"
    assert t['duration_days'] > 0, f"Expected duration_days > 0, got {t['duration_days']}"

print(">>> ALL BEST SWING TRADE INVARIANTS PASSED!")


print("\n==================================================================")
print("TEST 2: Empty Trades Edge Case")
print("==================================================================")
empty_analytics = compute_backtest_analytics([], capital_per_trade=100000.0)
empty_rep = empty_analytics.get('overall_report', {})
assert empty_rep.get('still_running_trades') == 0, "Expected 0 still running trades"
assert empty_rep.get('still_running_mtm') == 0.0, "Expected 0.0 still running MTM"
assert empty_rep.get('still_running_str') == "0 (₹ 0.00)", f"Expected '0 (₹ 0.00)', got {empty_rep.get('still_running_str')}"
print(">>> EMPTY TRADES REPORT PASSED!")


print("\n==================================================================")
print("TEST 3: Verify All Other Backtest Strategies")
print("==================================================================")
for s in bt_strats:
    name = s.get('name', '')
    print(f"Checking strategy: {name}")
    assert 'OPEN_TIMEOUT' not in s['code'] or '"is_open": False' in s['code'], f"OPEN_TIMEOUT with is_open: True found in {name}"
    # Ensure any simulate_trades or close_trade handles still running
    if 'close_trade(' in s['code']:
        assert "'exit_date': '-' if is_open" in s['code'] or '"exit_date": "-" if is_open' in s['code'], f"close_trade exit_date not updated in {name}"
        assert "'exit_reason': 'Still Running' if is_open" in s['code'] or '"exit_reason": "Still Running" if is_open' in s['code'], f"close_trade exit_reason not updated in {name}"

print(">>> ALL BACKTEST STRATEGIES PASSED!")

print("\n==================================================================")
print("TEST 4: FnO Symbol Fetch Offline / Online Test")
print("==================================================================")
from app import fetch_fno_symbols
fno_list = fetch_fno_symbols()
print(f"Total FnO symbols loaded: {len(fno_list)}")
assert len(fno_list) > 150, f"Expected >150 FnO symbols, got {len(fno_list)}"
assert 'RELIANCE' in fno_list
assert 'TCS' in fno_list
assert 'INFY' in fno_list
print(">>> FNO SYMBOLS TEST PASSED!")

print("\n==================================================================")
print("ALL VERIFICATION SUITES PASSED SUCCESSFULLY!")
print("==================================================================")

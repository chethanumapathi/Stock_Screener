import sys, os
sys.path.insert(0, os.path.abspath('.'))

from app import run_backtest_simulation, get_available_parquet_symbols
with open('strategies/fifteen_min_weekly_r3_r2_rsi80.py', 'r', encoding='utf-8') as f:
    orig_code = f.read()

symbols = ['ELECON'] + [s for s in get_available_parquet_symbols() if s != 'ELECON'][:120]

# Variation 1: 
# - No same-bar TP exit
# - INTRA_DAY_ONLY = True (square off 15:15)
# - Ensure curr_vwap < entry_price
v1_code = orig_code.replace(
    'INTRA_DAY_ONLY = False',
    'INTRA_DAY_ONLY = True'
).replace(
    'if not np.isnan(curr_vwap) and low[i] <= curr_vwap:\n                    exit_px = open_[i] if open_[i] <= curr_vwap else curr_vwap\n                    close_trade(i, exit_px, "Target Profit (Session VWAP Reached Same Bar)")\n                    state = "IDLE"',
    '# Same bar TP disabled to prevent lookahead/fill before breakout\n                    pass'
).replace(
    'if not np.isnan(curr_vwap) and low[i] <= curr_vwap:\n                exit_px = open_[i] if open_[i] <= curr_vwap else curr_vwap\n                close_trade(i, exit_px, "Target Profit (Session VWAP Reached)")',
    'if not np.isnan(curr_vwap) and curr_vwap < entry_price and low[i] <= curr_vwap:\n                exit_px = open_[i] if open_[i] <= curr_vwap else curr_vwap\n                close_trade(i, exit_px, "Target Profit (Session VWAP Reached)")'
)

res1 = run_backtest_simulation(
    code_str=v1_code,
    segment='watchlist',
    timeframe='5m',
    watchlist_symbols=symbols,
    start_date='2025-01-01',
    end_date='2026-05-15',
    capital_per_trade=100000.0,
    slippage_pct=0.5,
    include_brokerage=True,
    include_taxes=True,
    brokerage_per_order=20.0,
    min_market_cap_cr=0.0
)

trades1 = res1.get('trades', [])
tp1 = [t for t in trades1 if 'Target Profit' in t['exit_reason']]
pos_tp1 = [t for t in tp1 if t['net_pnl'] > 0]
neg_tp1 = [t for t in tp1 if t['net_pnl'] <= 0]

print(f"--- VARIATION 1 (Intraday, No Same-Bar TP, VWAP < Entry) ---")
print(f"Total Trades: {len(trades1)} | Win Rate: {res1.get('summary', {}).get('win_rate_pct')}% | Total PnL: Rs {res1.get('summary', {}).get('total_pnl_rupees')}")
print(f"Target Profit Trades: {len(tp1)} (Positive: {len(pos_tp1)}, Negative: {len(neg_tp1)})")

# Variation 2:
# - Also enforce a minimum profit buffer for TP (e.g. at least 1.5% drop to cover 1.0% slippage + taxes)
# or Target = min(VWAP, entry_price * 0.98) or VWAP <= entry_price * 0.985
v2_code = v1_code.replace(
    'if not np.isnan(curr_vwap) and curr_vwap < entry_price and low[i] <= curr_vwap:',
    'min_tp_target = entry_price * 0.985\n            target_level = min(curr_vwap, min_tp_target)\n            if not np.isnan(curr_vwap) and low[i] <= target_level:'
).replace(
    'exit_px = open_[i] if open_[i] <= curr_vwap else curr_vwap',
    'exit_px = open_[i] if open_[i] <= target_level else target_level'
)

res2 = run_backtest_simulation(
    code_str=v2_code,
    segment='watchlist',
    timeframe='5m',
    watchlist_symbols=symbols,
    start_date='2025-01-01',
    end_date='2026-05-15',
    capital_per_trade=100000.0,
    slippage_pct=0.5,
    include_brokerage=True,
    include_taxes=True,
    brokerage_per_order=20.0,
    min_market_cap_cr=0.0
)

trades2 = res2.get('trades', [])
tp2 = [t for t in trades2 if 'Target Profit' in t['exit_reason']]
pos_tp2 = [t for t in tp2 if t['net_pnl'] > 0]
neg_tp2 = [t for t in tp2 if t['net_pnl'] <= 0]

print(f"\n--- VARIATION 2 (Intraday, No Same-Bar TP, Min 1.5% Profit Buffer) ---")
print(f"Total Trades: {len(trades2)} | Win Rate: {res2.get('summary', {}).get('win_rate_pct')}% | Total PnL: Rs {res2.get('summary', {}).get('total_pnl_rupees')}")
print(f"Target Profit Trades: {len(tp2)} (Positive: {len(pos_tp2)}, Negative: {len(neg_tp2)})")

# Check ELECON on both
for idx, (lbl, res) in enumerate([("Var 1", res1), ("Var 2", res2)]):
    el_trades = [t for t in res.get('trades', []) if t['symbol'] == 'ELECON']
    print(f"\nELECON on {lbl}:")
    for t in el_trades:
        print(f"  Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} @ {t['exit_price']} | Reason: {t['exit_reason']} | Net PnL: Rs {t['net_pnl']}")

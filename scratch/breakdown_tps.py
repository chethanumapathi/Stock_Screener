import sys, os
sys.path.insert(0, os.path.abspath('.'))

from app import run_backtest_simulation, get_available_parquet_symbols
with open('strategies/fifteen_min_weekly_r3_r2_rsi80.py', 'r', encoding='utf-8') as f:
    code_str = f.read()

symbols = get_available_parquet_symbols()[:300]
res = run_backtest_simulation(
    code_str=code_str,
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

trades = res.get('trades', [])
tp_trades = [t for t in trades if 'Target Profit' in t['exit_reason']]

print(f"Total Trades: {len(trades)}")
print(f"Total Target Profit Trades: {len(tp_trades)}")

overnight_tps = []
same_bar_tps = []
micro_gain_tps = []
loss_tps = []
solid_gain_tps = []

for t in tp_trades:
    gross_pts = t['entry_price'] - t['exit_price']
    gross_pct = (gross_pts / t['entry_price']) * 100.0
    entry_d = t['entry_date'].split(' ')[0]
    exit_d = t['exit_date'].split(' ')[0]
    is_overnight = (entry_d != exit_d)
    is_same_bar = (t['entry_date'] == t['exit_date'])
    
    if gross_pct < 0:
        loss_tps.append((t, gross_pct, is_overnight))
    elif is_same_bar:
        same_bar_tps.append((t, gross_pct))
    elif gross_pct < 1.2:
        micro_gain_tps.append((t, gross_pct, is_overnight))
    else:
        solid_gain_tps.append((t, gross_pct, is_overnight))

print(f"\nBreakdown of 158 Target Profit trades:")
print(f"1. Outright Gross Loss (Exit > Entry): {len(loss_tps)} trades")
print(f"2. Same-bar exits (Entry = Exit bar): {len(same_bar_tps)} trades")
print(f"3. Micro-gains (0% to +1.2% gross, eaten by friction): {len(micro_gain_tps)} trades")
print(f"4. Solid gains (> +1.2% gross, positive net PnL): {len(solid_gain_tps)} trades")

print("\n--- Examples of Outright Gross Losses labeled Target Profit ---")
for t, g, ov in loss_tps[:5]:
    print(f"  {t['symbol']} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} @ {t['exit_price']} | Gross: {g:.2f}% | Net PnL: Rs {t['net_pnl']} | Overnight: {ov}")

print("\n--- Examples of Same-Bar Exits (0.00% gross) ---")
for t, g in same_bar_tps[:5]:
    print(f"  {t['symbol']} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} @ {t['exit_price']} | Net PnL: Rs {t['net_pnl']}")

print("\n--- Examples of Micro-Gains (Eaten by Slippage & Taxes) ---")
for t, g, ov in micro_gain_tps[:5]:
    print(f"  {t['symbol']} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} @ {t['exit_price']} | Gross: +{g:.2f}% | Net PnL: Rs {t['net_pnl']} | Overnight: {ov}")

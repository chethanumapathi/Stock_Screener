import os
import sys
sys.path.insert(0, os.path.abspath('.'))

import json
from app import run_backtest_simulation

def test_user_screenshot_symbols():
    print("=== Testing Short Strategy on User Screenshot Symbols ===")
    
    with open('strategies/intraday_rsi_volume_vwap_r2.py', 'r', encoding='utf-8') as f:
        code_str = f.read()

    symbols = ['LALPATHLAB', 'BHEL', 'TATATECH']
    
    result = run_backtest_simulation(
        code_str=code_str,
        segment='watchlist',
        timeframe='15m',
        watchlist_symbols=symbols,
        start_date='2026-05-01',
        end_date='2026-05-15',
        capital_per_trade=100000.0,
        slippage_pct=0.5,
        include_brokerage=True,
        include_taxes=True,
        brokerage_per_order=20.0,
        min_market_cap_cr=0.0
    )
    
    print("Status:", result.get('status'))
    trades = result.get('trades', [])
    print(f"Total trades: {len(trades)}")
    
    for t in trades:
        print(f"Trade #{t['trade_id']}: {t['symbol']} | Type: {t['type']} | Entry: {t['entry_date']} @ {t['entry_price']} | Exit: {t['exit_date']} @ {t['exit_price']} | Reason: {t['exit_reason']} | Net PnL: {t['net_pnl']} | PnL %: {t['pnl_pct']}%")
        assert t['type'] == 'Short', f"Expected Type 'Short', got {t['type']}"
        if 'Target Profit' in t['exit_reason']:
            assert t['net_pnl'] > 0, f"Expected positive Net PnL for TP, got {t['net_pnl']}"
            assert t['pnl_pct'] > 0, f"Expected positive PnL % for TP, got {t['pnl_pct']}"
            print(f"   -> VERIFIED TP PROFIT: {t['symbol']} made +Rs {t['net_pnl']} (+{t['pnl_pct']}%)")
        elif 'Stop Loss' in t['exit_reason']:
            assert t['net_pnl'] < 0, f"Expected negative Net PnL for SL, got {t['net_pnl']}"
            assert t['pnl_pct'] < 0, f"Expected negative PnL % for SL, got {t['pnl_pct']}"
            print(f"   -> VERIFIED SL LOSS: {t['symbol']} lost Rs {t['net_pnl']} ({t['pnl_pct']}%)")
            
    report = result.get('overall_report', {})
    print("\n=== Overall Report ===")
    print(f"Total Profit: Rs {report.get('overall_profit')}")
    print(f"Win Trades: {report.get('win_trades')} ({report.get('win_pct')}%)")
    print(f"Loss Trades: {report.get('loss_trades')} ({report.get('loss_pct')}%)")
    print(f"Max Drawdown: Rs {report.get('max_drawdown')}")
    
    assert report.get('win_trades', 0) >= 2, f"Expected at least 2 winning trades (LALPATHLAB & TATATECH), got {report.get('win_trades')}"
    assert report.get('loss_trades', 0) >= 1, f"Expected at least 1 losing trade (BHEL), got {report.get('loss_trades')}"
    print("\nALL SHORT TRADES, PnL, TYPE, AND OVERALL REPORT VERIFIED PERFECTLY!")

if __name__ == '__main__':
    test_user_screenshot_symbols()

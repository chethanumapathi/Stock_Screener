import urllib.request
import json
import os
import sys

def run_test():
    with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
        strats = json.load(f)

    # Find the two target strategies
    strat1 = next((s for s in strats if 'Daily Monthly-R3' in s['name']), None)
    strat2 = next((s for s in strats if 'Weekly Yearly-R1' in s['name']), None)

    targets = []
    if strat1: targets.append(("Report 1: Daily Monthly-R3 Breakout above Yearly-R2", strat1))
    if strat2: targets.append(("Report 2: Best Swing Trade - Weekly Yearly-R1 Breakout", strat2))

    for label, strat in targets:
        print(f"\n=======================================================================")
        print(f"TESTING {label}")
        print(f"=======================================================================")
        
        payload = json.dumps({
            'code': strat['code'],
            'segment': 'nifty50',
            'timeframe': '1d',
            'start_date': '2023-01-01',
            'end_date': '2026-09-20'
        }).encode('utf-8')

        req = urllib.request.Request('http://127.0.0.1:8000/api/backtest', data=payload, headers={'Content-Type': 'application/json'})
        res = urllib.request.urlopen(req, timeout=120)
        data = json.loads(res.read().decode())
        
        status = data.get('status')
        trades = data.get('trades', [])
        rep = data.get('overall_report', {})
        print(f"Backtest Status: {status} | Total Trades: {len(trades)}")
        print(f"Headline Net Profit: Rs {rep.get('overall_profit', 0.0):,.2f} | Max DD: Rs {rep.get('max_drawdown', 0.0):,.2f}")
        print(f"Duration of MDD: {rep.get('duration_of_max_drawdown')}")

        # Call diagnostics endpoint to get full diagnostics suite
        diag_payload = json.dumps({
            'trades': trades,
            'capital_per_trade': 100000.0,
            'slippage_pct': 0.5,
            'include_brokerage': True,
            'include_taxes': True,
            'brokerage_per_order': 20.0
        }).encode('utf-8')
        
        d_req = urllib.request.Request('http://127.0.0.1:8000/api/backtest/diagnostics', data=diag_payload, headers={'Content-Type': 'application/json'})
        d_res = urllib.request.urlopen(d_req, timeout=120)
        d_data = json.loads(d_res.read().decode())
        diag = d_data.get('diagnostics', {})

        # 1. Check OOS split
        oos = diag.get('out_of_sample_split', {})
        is_info = oos.get('in_sample', {})
        oos_info = oos.get('out_of_sample', {})
        print(f"\n--- Issue 1: OOS Split (by entry date) ---")
        print(f"Split Date: {oos.get('split_date')}")
        print(f"IS Trades: {is_info.get('trades')} ({is_info.get('start_date')} to {is_info.get('end_date')})")
        print(f"OOS Trades: {oos_info.get('trades')} ({oos_info.get('start_date')} to {oos_info.get('end_date')})")
        print(f"Degradation Ratio: {oos.get('degradation_ratio')} | Status: {oos.get('status')}")

        # 2. Check Regime Breakdown
        regime = diag.get('regime_split', {})
        reg_list = regime.get('regimes', [])
        print(f"\n--- Issue 4: Market Regime Breakdown ---")
        for r in reg_list:
            print(f"  {r.get('regime')}: {r.get('trades')} trades | Win%: {r.get('win_pct')}% | Profit: Rs {r.get('net_profit', 0):,.0f}")

        # 3. Check Beta & Correlation
        bm = diag.get('benchmark') or diag.get('benchmark_comparison') or {}
        print(f"\n--- Issue 5: Benchmark Beta & Correlation ---")
        print(f"Beta: {bm.get('beta')} | Correlation (r): {bm.get('correlation')} | Strat CAGR: {bm.get('strategy_cagr')}% | Nifty CAGR: {bm.get('nifty_cagr')}%")

        # 4. Check Position Sizing
        pos = diag.get('position_sizing', {})
        models = pos.get('models', {})
        fixed_m = models.get('fixed', {})
        comp_m = models.get('compounding', {})
        vol_m = models.get('volatility_scaled', {})
        print(f"\n--- Issue 6: Position Sizing Table ---")
        print(f"Fixed Net Profit: Rs {fixed_m.get('net_profit', 0.0):,.2f} (Headline matches: {abs(fixed_m.get('net_profit', 0.0) - rep.get('overall_profit', 0.0)) < 1.0})")
        print(f"Compounding Status: {comp_m.get('status')} | Volatility Status: {vol_m.get('status')}")

        # 5. Check Fat Tail text
        pnl_dist = diag.get('pnl_distribution', {})
        print(f"\n--- Issue 7: Fat Tail Dynamic Text ---")
        print(f"Comment: {pnl_dist.get('fat_tail_comment')}")

        # 6. Check Monte Carlo
        mc = diag.get('monte_carlo', {})
        mc_stats = mc.get('stats', {})
        print(f"\n--- Issue 9: Monte Carlo Stress Risk ---")
        print(f"Median MDD: Rs {mc_stats.get('median_mdd', 0.0):,.2f} | 95th MDD: Rs {mc_stats.get('p95_worst_case_mdd', 0.0):,.2f}")
        print(f"P(DD > Historical MDD): {mc_stats.get('prob_exceed_hist_mdd')}% (Hist MDD: Rs {mc_stats.get('hist_mdd', 0.0):,.2f})")

        # 7. Test PDF Generation
        print(f"\n--- PDF Generation Test ---")
        pdf_payload = json.dumps({
            'report_data': {
                'trades': trades,
                'overall_report': rep,
                'year_wise_returns': data.get('year_wise_returns', []),
                'drawdown_chart': data.get('drawdown_chart', {}),
                'diagnostics': diag,
                'summary': data.get('summary', {}),
                'timeframe': data.get('timeframe', '1d')
            },
            'strategy_name': strat['name']
        }).encode('utf-8')
        
        p_req = urllib.request.Request('http://127.0.0.1:8000/api/export-backtest-pdf', data=pdf_payload, headers={'Content-Type': 'application/json'})
        p_res = urllib.request.urlopen(p_req, timeout=120)
        pdf_bytes = p_res.read()
        print(f"PDF Successfully Generated! Size: {len(pdf_bytes):,} bytes")

if __name__ == '__main__':
    run_test()

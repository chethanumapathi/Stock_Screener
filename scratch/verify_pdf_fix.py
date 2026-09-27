import sys
sys.path.append('.')
import json
from app import compute_backtest_analytics, generate_backtest_pdf

with open('scratch/sample_backtest_result.json', 'r') as f:
    sample_data = json.load(f)

trades = sample_data.get('trades', [])
print(f"Testing compute_backtest_analytics on {len(trades)} trades...")
analytics_result = compute_backtest_analytics(trades, capital_per_trade=100000.0)

rep = analytics_result['overall_report']
print("\nUpdated overall_report drawdown metrics:")
print("  Max Drawdown:", rep.get('max_drawdown'))
print("  Duration of Max DD:", rep.get('duration_of_max_drawdown'))
print("  Longest Underwater Period:", rep.get('longest_underwater_period'))
print("  MDD Total Days:", rep.get('mdd_total_days'))
print("  MDD Fall Days:", rep.get('mdd_contraction_days'))
print("  MDD Recovery Days:", rep.get('mdd_recovery_days'))
print("  Time Under Water %:", rep.get('time_under_water_pct'))

# Test PDF generation
analytics_result['strategy_name'] = "Test Enhanced Drawdown Strategy"
analytics_result['timeframe'] = "1D"
pdf_bytes = generate_backtest_pdf(analytics_result)
print(f"\nSuccessfully generated PDF report! Size: {len(pdf_bytes)} bytes.")

with open('scratch/test_enhanced_report.pdf', 'wb') as f:
    f.write(pdf_bytes)
print("Saved to scratch/test_enhanced_report.pdf")

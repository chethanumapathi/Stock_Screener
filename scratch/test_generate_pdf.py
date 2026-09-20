import io
import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import pandas as pd
import numpy as np

from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as RLImage

def parse_date_flexible(d_str):
    if not d_str or str(d_str).strip() in ['-', 'None', 'nan', '']:
        return None
    s = str(d_str).strip()
    # Check if there is time portion or extra text
    if ' ' in s:
        s = s.split(' ')[0]
    for fmt in ('%d-%b-%Y', '%Y-%m-%d', '%d-%m-%Y', '%Y/%m/%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return pd.to_datetime(s).to_pydatetime()
    except Exception:
        return None

def build_complete_pdf(report_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=20,
        bottomMargin=20
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=3
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        textColor=colors.HexColor('#475569'),
        spaceAfter=8
    )
    section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=8,
        spaceAfter=4
    )
    banner_style = ParagraphStyle(
        'BannerTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=4,
        spaceAfter=6
    )
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor('#1e293b')
    )
    
    elements = []
    
    # ----------------------------------------------------
    # PAGE 1: TITLE, OVERALL REPORT & YEAR-WISE RETURNS
    # ----------------------------------------------------
    strat_name = report_data.get('strategy_name', 'Backtest Strategy')
    timeframe = str(report_data.get('timeframe', '1d')).upper()
    capital = float(report_data.get('capital_per_trade', 100000.0))
    slippage = float(report_data.get('slippage_pct', 0.5))
    brokerage = float(report_data.get('brokerage_per_order', 20.0))
    gen_time = datetime.now().strftime('%d-%b-%Y %H:%M')
    
    elements.append(Paragraph(f"<b>Backtest Performance Report: {strat_name}</b>", title_style))
    meta_text = (
        f"Timeframe: <b>{timeframe}</b> | Capital/Trade: <b>Rs {capital:,.2f}</b> | "
        f"Slippage: <b>{slippage}%</b> | Brokerage: <b>Rs {brokerage:.1f}/order</b> | Generated: <b>{gen_time}</b>"
    )
    elements.append(Paragraph(meta_text, subtitle_style))
    
    rep = report_data.get('overall_report', {})
    ov_profit = rep.get('overall_profit', 0.0)
    profit_color = colors.HexColor('#16a34a') if ov_profit >= 0 else colors.HexColor('#dc2626')
    
    # Format win & loss counts
    win_cnt = rep.get('win_trades', 0)
    loss_cnt = rep.get('loss_trades', 0)
    win_pct = rep.get('win_pct', 0.0)
    loss_pct = rep.get('loss_pct', 0.0)
    win_loss_display = f"{win_cnt} ({win_pct:.1f}%) / {loss_cnt} ({loss_pct:.1f}%)"
    
    col1 = [
        ["Returns & Win Rates", "Value"],
        ["Overall Profit / Loss", f"Rs {ov_profit:,.2f}"],
        ["CAGR / Ann. Return", f"{rep.get('cagr_pct', 0.0):.2f}%"],
        ["Closed Trades", str(rep.get('no_of_trades', 0))],
        ["Running Trades (EOD)", str(rep.get('open_trades', 0))],
        ["Win / Loss Trades", win_loss_display],
        ["Avg Profit / Trade", f"Rs {rep.get('avg_profit_per_trade', 0.0):,.2f}"],
        ["Avg Win", f"Rs {rep.get('avg_profit_on_winning', 0.0):,.2f}"],
        ["Avg Loss", f"Rs {rep.get('avg_loss_on_losing', 0.0):,.2f}"],
    ]
    col2 = [
        ["Risk-Adjusted Ratios", "Value"],
        ["Profit Factor", f"{rep.get('profit_factor', 0.0):.2f}"],
        ["Calmar Ratio", f"{rep.get('calmar_ratio', 0.0):.2f}"],
        ["Sharpe Ratio (Ann.)", f"{rep.get('sharpe_ratio', 0.0):.2f}"],
        ["Sortino Ratio (Ann.)", f"{rep.get('sortino_ratio', 0.0):.2f}"],
        ["Recovery Factor", f"{rep.get('recovery_factor', 0.0):.2f}x"],
        ["Ulcer Index (UI)", f"{rep.get('ulcer_index', 0.0):.2f}"],
        ["Reward to Risk", f"{rep.get('reward_to_risk_ratio', 0.0):.2f}"],
        ["Expectancy Ratio", f"{rep.get('expectancy_ratio', 0.0):.2f}"],
        ["Max Drawdown", f"Rs {rep.get('max_drawdown', 0.0):,.2f}"],
    ]
    col3 = [
        ["Capital & Exposure", "Value"],
        ["Peak Capital Deployed", f"Rs {rep.get('peak_capital_deployed', 0.0):,.0f}"],
        ["Max Concurrent Pos", str(rep.get('max_concurrent_positions', 1))],
        ["Capital Utilization", f"{rep.get('capital_utilization_pct', 0.0):.1f}%"],
        ["Top 5 Concentration", str(rep.get('symbol_concentration_str', '-'))[:18]],
        ["Max Trades in DD", str(rep.get('max_trades_in_drawdown', 0))],
        ["Max Single Profit", f"Rs {rep.get('max_profit_single', 0.0):,.2f}"],
        ["Max Single Loss", f"Rs {rep.get('max_loss_single', 0.0):,.2f}"],
        ["Duration of Max DD", str(rep.get('duration_of_max_drawdown', '-'))[:15]],
        ["Return over Max DD", f"{rep.get('return_over_max_dd', 0.0):.2f}"],
    ]
    col4 = [
        ["Trade Quality & Consistency", "Value"],
        ["Time Under Water %", f"{rep.get('time_under_water_pct', 0.0):.1f}%"],
        ["Avg MAE (Adverse)", f"-{rep.get('avg_mae_pct', 0.0):.2f}%"],
        ["Avg MFE (Favorable)", f"+{rep.get('avg_mfe_pct', 0.0):.2f}%"],
        ["Profitable Months", str(rep.get('profitable_months_str', '-'))],
        ["Avg Hold (Winners)", f"{rep.get('avg_holding_win_days', 0.0):.1f}d"],
        ["Avg Hold (Losers)", f"{rep.get('avg_holding_loss_days', 0.0):.1f}d"],
        ["Max Win Streak", str(rep.get('max_win_streak', 0))],
        ["Max Losing Streak", str(rep.get('max_losing_streak', 0))],
        ["Slippage / Brokerage", f"{slippage}% / Rs{brokerage:.0f}"],
    ]
    
    def make_sub_table(data_matrix, highlight_first_val=False):
        t = Table(data_matrix, colWidths=[118, 80])
        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ]
        if highlight_first_val:
            t_style.append(('TEXTCOLOR', (1, 1), (1, 1), profit_color))
            t_style.append(('FONTNAME', (1, 1), (1, 1), 'Helvetica-Bold'))
        t.setStyle(TableStyle(t_style))
        return t
        
    t1 = make_sub_table(col1, highlight_first_val=True)
    t2 = make_sub_table(col2)
    t3 = make_sub_table(col3)
    t4 = make_sub_table(col4)
    
    elements.append(Paragraph("<b>Executive Performance Summary</b>", section_title))
    summary_table = Table([[t1, t2, t3, t4]], colWidths=[198, 198, 198, 198])
    summary_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 6))
    
    # Year-wise Matrix Table
    elements.append(Paragraph("<b>Year-wise & Month-wise Returns (Rs)</b>", section_title))
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    headers = ['Year'] + months + ['Total', 'Max DD', 'Days for MDD', 'CAGR']
    
    rows_data = [headers]
    yw_rows = report_data.get('year_wise_returns', [])
    
    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('LINEAFTER', (0, 0), (0, -1), 1, colors.HexColor('#94a3b8')),
        ('LINEAFTER', (12, 0), (12, -1), 1.5, colors.HexColor('#64748b')),
        ('LINEAFTER', (13, 0), (13, -1), 1, colors.HexColor('#94a3b8')),
    ]
    
    for row_idx, r in enumerate(yw_rows, start=1):
        year_str = str(r.get('year', ''))
        m_vals = [f"{r.get(m, 0):,.0f}" if r.get(m, 0) != 0 else '-' for m in months]
        tot = r.get('total', 0)
        tot_str = f"{tot:,.0f}" if tot != 0 else '-'
        mdd = r.get('max_drawdown', 0)
        mdd_str = f"{mdd:,.0f}" if mdd != 0 else '-'
        days_str = str(r.get('days_for_mdd', '-'))
        cagr_val = r.get('cagr', 0.0)
        cagr_str = f"{cagr_val:+.2f}%" if cagr_val != 0 else "0.00%"
        
        row_cells = [year_str] + m_vals + [tot_str, mdd_str, days_str, cagr_str]
        rows_data.append(row_cells)
        
        bg = colors.HexColor('#f8fafc') if row_idx % 2 == 1 else colors.white
        style_commands.append(('BACKGROUND', (0, row_idx), (-1, row_idx), bg))
        
        tot_color = colors.HexColor('#16a34a') if tot > 0 else (colors.HexColor('#dc2626') if tot < 0 else colors.HexColor('#64748b'))
        style_commands.append(('TEXTCOLOR', (13, row_idx), (13, row_idx), tot_color))
        style_commands.append(('FONTNAME', (13, row_idx), (13, row_idx), 'Helvetica-Bold'))
        
        cagr_color = colors.HexColor('#16a34a') if cagr_val > 0 else (colors.HexColor('#dc2626') if cagr_val < 0 else colors.HexColor('#64748b'))
        style_commands.append(('TEXTCOLOR', (16, row_idx), (16, row_idx), cagr_color))
        style_commands.append(('FONTNAME', (16, row_idx), (16, row_idx), 'Helvetica-Bold'))
        
        for m_col_idx, m in enumerate(months, start=1):
            m_val = r.get(m, 0)
            if m_val > 0:
                style_commands.append(('TEXTCOLOR', (m_col_idx, row_idx), (m_col_idx, row_idx), colors.HexColor('#16a34a')))
            elif m_val < 0:
                style_commands.append(('TEXTCOLOR', (m_col_idx, row_idx), (m_col_idx, row_idx), colors.HexColor('#dc2626')))
                
    if len(rows_data) == 1:
        rows_data.append(['No data'] + ['-'] * 16)
        
    col_w = [38] + [42]*12 + [54, 52, 72, 46]
    matrix_table = Table(rows_data, colWidths=col_w)
    matrix_table.setStyle(TableStyle(style_commands))
    elements.append(matrix_table)
    
    summary = report_data.get('summary', {})
    tot_brok = summary.get('total_brokerage', 0.0)
    tot_tax = summary.get('total_taxes', 0.0)
    elements.append(Spacer(1, 4))
    footer_text = f"Total Estimated Brokerage: <b>Rs {tot_brok:,.2f}</b> | Total Taxes & Regulatory Charges: <b>Rs {tot_tax:,.2f}</b>"
    elements.append(Paragraph(footer_text, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7.5, textColor=colors.HexColor('#64748b'))))
    
    # ----------------------------------------------------
    # PAGE 2: ROBUSTNESS & VALIDATION SUITE
    # ----------------------------------------------------
    diag = report_data.get('diagnostics', {})
    elements.append(PageBreak())
    elements.append(Paragraph("<b>🛡️ Robustness & Validation Suite</b>", banner_style))
    
    # 1. Benchmark Comparison (Nifty 50)
    bench = diag.get('benchmark_comparison', {})
    elements.append(Paragraph("<b>1. Benchmark Comparison (Nifty 50 Index)</b>", section_title))
    
    strat_cagr = bench.get('strategy_cagr', 0.0)
    nifty_cagr = bench.get('nifty_cagr', 0.0)
    alpha = bench.get('alpha', 0.0)
    beta = bench.get('beta', 0.0)
    corr = bench.get('correlation', 0.0)
    
    bench_rows = [
        ["Metric", "Strategy Portfolio", "Nifty 50 Benchmark", "Relative Edge / Interpretation"],
        ["CAGR / Ann. Return", f"{strat_cagr:+.2f}%", f"{nifty_cagr:+.2f}%", f"{strat_cagr - nifty_cagr:+.2f}% Outperformance"],
        ["Annualized Alpha (α)", f"{alpha:+.2f}%", "—", "Excess risk-adjusted return over market exposure"],
        ["Beta to Nifty 50 (β)", f"{beta:.2f}", "1.00", "Market sensitivity (< 0.50 indicates high diversification)"],
        ["Correlation (r)", f"{corr:.2f}", "1.00", "Daily return co-movement (-1.00 to +1.00)"]
    ]
    t_bench = Table(bench_rows, colWidths=[160, 150, 150, 332])
    t_bench.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('ALIGN', (1, 0), (2, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t_bench)
    elements.append(Spacer(1, 6))
    
    # 2. Out-of-Sample / Walk-Forward Split
    oos = diag.get('out_of_sample_split', {})
    elements.append(Paragraph("<b>2. Out-of-Sample / Walk-Forward Split (65% In-Sample / 35% Out-of-Sample)</b>", section_title))
    
    is_data = oos.get('in_sample', {})
    oos_data = oos.get('out_of_sample', {})
    deg_ratio = oos.get('degradation_ratio', 0.0)
    deg_pct = round(deg_ratio * 100, 1)
    
    oos_rows = [
        ["Performance Metric", "In-Sample (Train 65%)", "Out-of-Sample (Test 35%)", f"Edge Retention (Degradation Ratio: {deg_ratio:.2f})"],
        ["Closed Trades", str(is_data.get('trades', 0)), str(oos_data.get('trades', 0)), f"{oos_data.get('trades', 0) / max(1, is_data.get('trades', 1)) * 100:.1f}% sample size"],
        ["Win Rate %", f"{is_data.get('win_pct', 0.0):.1f}%", f"{oos_data.get('win_pct', 0.0):.1f}%", f"{oos_data.get('win_pct', 0.0) - is_data.get('win_pct', 0.0):+.1f}% variance"],
        ["Profit Factor", f"{is_data.get('profit_factor', 0.0):.2f}", f"{oos_data.get('profit_factor', 0.0):.2f}", f"{oos_data.get('profit_factor', 0.0) / max(0.01, is_data.get('profit_factor', 1)):.2f}x retention"],
        ["CAGR %", f"{is_data.get('cagr_pct', 0.0):+.2f}%", f"{oos_data.get('cagr_pct', 0.0):+.2f}%", f"{oos_data.get('cagr_pct', 0.0) - is_data.get('cagr_pct', 0.0):+.2f}% annualized diff"],
        ["Expectancy Ratio", f"{is_data.get('expectancy', 0.0):.2f}", f"{oos_data.get('expectancy', 0.0):.2f}", f"{oos_data.get('expectancy', 0.0) / max(0.01, is_data.get('expectancy', 1)):.2f}x retention"],
        ["Max Drawdown (Rs)", f"Rs {is_data.get('max_drawdown', 0.0):,.0f}", f"Rs {oos_data.get('max_drawdown', 0.0):,.0f}", "Downside risk comparison"]
    ]
    t_oos = Table(oos_rows, colWidths=[160, 150, 150, 332])
    t_oos.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('ALIGN', (1, 0), (2, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t_oos)
    elements.append(Spacer(1, 6))
    
    # 3. Monte Carlo Simulation (1,000x Bootstrap Resampling)
    mc = diag.get('monte_carlo', {})
    mc_stats = mc.get('stats', {})
    elements.append(Paragraph("<b>3. Monte Carlo Simulation (1,000 Randomized Bootstrap Resamplings)</b>", section_title))
    
    mc_rows = [
        ["Monte Carlo Stress Metric", "Simulated Level", "Institutional Risk Assessment"],
        ["Median Max Drawdown", f"Rs {mc_stats.get('median_mdd', 0.0):,.2f}", "Typical expected drawdown across 50% of simulated alternative histories"],
        ["95th %ile Worst Drawdown", f"Rs {mc_stats.get('p95_worst_case_mdd', 0.0):,.2f}", "Value-at-Risk boundary (Only 5% chance of worse drawdown under trade reshuffle)"],
        ["99th %ile Stress Drawdown", f"Rs {mc_stats.get('p99_stress_mdd', 0.0):,.2f}", "Extreme tail-risk stress boundary (1-in-100 adverse trade clustering)"],
        ["Probability (Drawdown > 20%)", f"{mc_stats.get('prob_mdd_over_20pct', 0.0):.1f}%", "Likelihood of severe capital impairment (> 20% equity drawdown)"]
    ]
    t_mc = Table(mc_rows, colWidths=[200, 160, 432])
    t_mc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TEXTCOLOR', (1, 1), (1, 3), colors.HexColor('#dc2626')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t_mc)
    elements.append(Spacer(1, 6))
    
    # 4. Market Regime Breakdown
    regime = diag.get('regime_split', {})
    regime_list = regime.get('regimes', [])
    elements.append(Paragraph("<b>4. Market Regime Breakdown (Nifty 50 200 SMA Trend)</b>", section_title))
    
    reg_rows = [["Market Regime", "Trades", "Win Rate %", "Profit Factor", "Net Profit (Rs)", "Avg Profit / Trade"]]
    for rg in regime_list:
        p_color_hex = '#16a34a' if rg.get('net_profit', 0) >= 0 else '#dc2626'
        reg_rows.append([
            rg.get('regime', '-'),
            str(rg.get('trades', 0)),
            f"{rg.get('win_pct', 0.0):.1f}%",
            f"{rg.get('profit_factor', 0.0):.2f}",
            f"Rs {rg.get('net_profit', 0.0):,.2f}",
            f"Rs {rg.get('avg_profit_trade', 0.0):,.2f}"
        ])
    if len(reg_rows) == 1:
        reg_rows.append(["No regime data", "-", "-", "-", "-", "-"])
        
    t_reg = Table(reg_rows, colWidths=[180, 80, 100, 110, 160, 162])
    t_reg.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(t_reg)
    
    # ----------------------------------------------------
    # PAGE 3: TRADE & PORTFOLIO DIAGNOSTICS
    # ----------------------------------------------------
    elements.append(PageBreak())
    elements.append(Paragraph("<b>📊 Trade & Portfolio Diagnostics</b>", banner_style))
    
    # 1. Position Sizing Comparison
    pos_sizing = diag.get('position_sizing', {})
    models = pos_sizing.get('models', {})
    elements.append(Paragraph("<b>1. Position Sizing Models Comparison</b>", section_title))
    
    m_fixed = models.get('fixed', {})
    m_comp = models.get('compounding', {})
    m_vol = models.get('volatility_scaled', {})
    
    pos_rows = [
        ["Model Architecture", "Capital Allocation Sizing Logic", "Net Profit (Rs)", "Max Drawdown %", "CAGR %", "Final Capital (Rs)"],
        ["Fixed Capital per Trade", f"Rs {capital:,.0f} baseline allocation per signal", f"Rs {m_fixed.get('net_profit', 0.0):,.2f}", f"{m_fixed.get('max_dd_pct', 0.0):.2f}%", f"{m_fixed.get('cagr_pct', 0.0):.2f}%", f"Rs {m_fixed.get('final_equity', 0.0):,.2f}"],
        ["Compounding Active Equity", "5% dynamic reinvestment of running active equity", f"Rs {m_comp.get('net_profit', 0.0):,.2f}", f"{m_comp.get('max_dd_pct', 0.0):.2f}%", f"{m_comp.get('cagr_pct', 0.0):.2f}%", f"Rs {m_comp.get('final_equity', 0.0):,.2f}"],
        ["Volatility / ATR-Scaled", "0.5% account risk scaled by ATR stop distance", f"Rs {m_vol.get('net_profit', 0.0):,.2f}", f"{m_vol.get('max_dd_pct', 0.0):.2f}%", f"{m_vol.get('cagr_pct', 0.0):.2f}%", f"Rs {m_vol.get('final_equity', 0.0):,.2f}"]
    ]
    t_pos = Table(pos_rows, colWidths=[150, 192, 110, 100, 90, 150])
    t_pos.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t_pos)
    elements.append(Spacer(1, 8))
    
    # 2. Sector & Market Cap Concentration (Two side-by-side tables)
    elements.append(Paragraph("<b>2. Sector & Market Capitalization Concentration</b>", section_title))
    sec_mcap = diag.get('sector_mcap', {})
    mcap_list = sec_mcap.get('market_cap', [])
    sector_list = sec_mcap.get('sectors', [])
    
    mcap_rows = [["Market Cap Tier", "Trades", "Win %", "Net Profit (Rs)"]]
    for mc_item in mcap_list:
        mcap_rows.append([
            mc_item.get('tier', '-'),
            str(mc_item.get('trades', 0)),
            f"{mc_item.get('win_pct', 0.0):.1f}%",
            f"Rs {mc_item.get('profit', 0.0):,.0f}"
        ])
    if len(mcap_rows) == 1:
        mcap_rows.append(["No Mcap Data", "-", "-", "-"])
        
    t_mcap = Table(mcap_rows, colWidths=[140, 60, 60, 110])
    t_mcap.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    
    sec_rows = [["Top Sectors", "Trades", "Win %", "Net Profit (Rs)"]]
    for s_item in sector_list[:5]:
        sec_rows.append([
            str(s_item.get('sector', '-'))[:22],
            str(s_item.get('trades', 0)),
            f"{s_item.get('win_pct', 0.0):.1f}%",
            f"Rs {s_item.get('profit', 0.0):,.0f}"
        ])
    if len(sec_rows) == 1:
        sec_rows.append(["No Sector Data", "-", "-", "-"])
        
    t_sec = Table(sec_rows, colWidths=[172, 60, 60, 110])
    t_sec.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    
    side_by_side = Table([[t_mcap, t_sec]], colWidths=[385, 407])
    side_by_side.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(side_by_side)
    elements.append(Spacer(1, 8))
    
    # 3. P&L Distribution, Skewness, Kurtosis & Capital Exposure
    pnl_dist = diag.get('pnl_distribution', {})
    timeline = diag.get('concurrent_timeline', {})
    elements.append(Paragraph("<b>3. Trade Return Distribution & Portfolio Dynamics</b>", section_title))
    
    skew = pnl_dist.get('skewness', 0.0)
    kurt = pnl_dist.get('kurtosis', 0.0)
    fat_tail = pnl_dist.get('fat_tail_comment', '-')
    peak_pos = timeline.get('peak_positions', 0)
    avg_util = timeline.get('avg_utilization', 0.0)
    
    dist_rows = [
        ["Diagnostic Parameter", "Calculated Value", "Statistical & Operational Meaning"],
        ["Return Skewness", f"{skew:+.2f}", "Positive skew: Right-tailed payoff (occasional massive winners, tightly capped losses)"],
        ["Excess Kurtosis", f"{kurt:+.2f}", "Leptokurtic fat tails: Higher frequency of outlier trend moves than normal Gaussian curve"],
        ["Fat Tail Risk Assessment", str(fat_tail), "Identifies whether profits rely on rare outlier multi-bagger runners"],
        ["Peak Concurrent Positions", str(peak_pos), f"Maximum simultaneous open trades (Required peak liquidity: Rs {peak_pos * capital:,.0f})"],
        ["Average Capital Utilized", f"{avg_util:.1f}%", f"Time-weighted mean capital deployed (Remaining {100 - avg_util:.1f}% in liquid reserves)"]
    ]
    t_dist = Table(dist_rows, colWidths=[180, 140, 472])
    t_dist.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#f8fafc')),
    ]))
    elements.append(t_dist)
    
    # ----------------------------------------------------
    # PAGE 4: UNDERWATER DRAWDOWN ANALYSIS & TIMELINE CHART
    # ----------------------------------------------------
    dd_data = report_data.get('drawdown_chart', {})
    dd_dates = dd_data.get('dates', [])
    dd_vals = dd_data.get('drawdowns', [])
    
    if dd_dates and dd_vals:
        elements.append(PageBreak())
        elements.append(Paragraph("<b>Underwater Drawdown Analysis & Timeline</b>", banner_style))
        
        mdd_val = rep.get('max_drawdown', 0.0)
        mdd_dur = rep.get('duration_of_max_drawdown', '-')
        trades_in_dd = rep.get('max_trades_in_drawdown', 0)
        ret_mdd = rep.get('return_over_max_dd', 0.0)
        rec_fac = rep.get('recovery_factor', 0.0)
        ulc_idx = rep.get('ulcer_index', 0.0)
        tuw_pct = rep.get('time_under_water_pct', 0.0)
        
        dd_summary_matrix = [
            ["Max Drawdown (Rs)", "Duration of MDD", "Max Trades in DD", "Return / Max DD", "Recovery Factor", "Ulcer Index (UI)", "Time Under Water %"],
            [f"Rs {mdd_val:,.2f}", str(mdd_dur), str(trades_in_dd), f"{ret_mdd:.2f}", f"{rec_fac:.2f}x", f"{ulc_idx:.2f}", f"{tuw_pct:.1f}%"]
        ]
        dd_summary_table = Table(dd_summary_matrix, colWidths=[118, 128, 106, 110, 110, 110, 110])
        dd_summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TEXTCOLOR', (0, 1), (0, 1), colors.HexColor('#dc2626')),
        ]))
        elements.append(dd_summary_table)
        elements.append(Spacer(1, 10))
        
        try:
            fig, ax = plt.subplots(figsize=(10.5, 3.8), dpi=130)
            fig.patch.set_facecolor('#ffffff')
            ax.set_facecolor('#f8fafc')
            
            parsed_dates = []
            valid_vals = []
            for d_str, v in zip(dd_dates, dd_vals):
                try:
                    dt = parse_date_flexible(d_str)
                    if dt:
                        parsed_dates.append(dt)
                        valid_vals.append(float(v))
                except Exception:
                    continue
                    
            if parsed_dates:
                ax.plot(parsed_dates, valid_vals, color='#ef4444', linewidth=1.5, label='Underwater Drawdown (Rs)')
                ax.fill_between(parsed_dates, 0, valid_vals, color='#ef4444', alpha=0.18)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
                fig.autofmt_xdate(rotation=20)
                ax.grid(True, linestyle='--', alpha=0.5, color='#cbd5e1')
                ax.axhline(0, color='#64748b', linestyle='-', linewidth=0.8)
                ax.set_ylabel('Drawdown (Rs)', fontsize=9, fontweight='bold', color='#334155')
                ax.set_title('Continuous Underwater Drawdown Timeline Over Strategy Horizon', fontsize=11, fontweight='bold', color='#0f172a', pad=10)
                ax.legend(loc='lower left', framealpha=0.9, fontsize=8)
                
                plt.tight_layout()
                chart_buf = io.BytesIO()
                fig.savefig(chart_buf, format='png', bbox_inches='tight')
                plt.close(fig)
                chart_buf.seek(0)
                
                elements.append(RLImage(chart_buf, width=780, height=270))
        except Exception as e:
            print(f"Failed to plot drawdown chart for PDF: {e}")
            
    def add_page_decorations(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#94a3b8'))
        canvas.drawString(24, 10, "ChethanQuant Institutional Backtest & Diagnostics Report | Confidential")
        canvas.drawRightString(842 - 24, 10, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_page_decorations, onLaterPages=add_page_decorations)
    print(f"ReportLab generated {doc.page} pages.")
    buffer.seek(0)
    return buffer.getvalue()

if __name__ == '__main__':
    with open('scratch/sample_backtest_result.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    data['strategy_name'] = 'Weekly Yearly-R1 Breakout Strategy'
    pdf_bytes = build_complete_pdf(data)
    with open('scratch/test_backtest_report.pdf', 'wb') as f:
        f.write(pdf_bytes)
    print(f"Successfully generated scratch/test_backtest_report.pdf ({len(pdf_bytes):,} bytes)")

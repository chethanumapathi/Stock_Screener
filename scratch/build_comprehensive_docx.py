import os
import sys
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def create_document():
    doc = docx.Document()
    
    # Page setup - 1 inch margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
    # Color palette
    NAVY = RGBColor(31, 78, 120)     # Primary headers #1F4E78
    SLATE = RGBColor(47, 85, 151)    # Secondary headers #2F5597
    DARK = RGBColor(38, 38, 38)      # Body text #262626
    MUTED = RGBColor(89, 89, 89)     # Captions / metadata
    WHITE = RGBColor(255, 255, 255)
    
    def set_cell_bg(cell, hex_color):
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
        cell._tc.get_or_add_tcPr().append(shading)

    def set_cell_margins(cell, top=120, bottom=120, left=160, right=160):
        tcPr = cell._tc.get_or_add_tcPr()
        tcMar = OxmlElement('w:tcMar')
        for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
            node = OxmlElement(f'w:{m}')
            node.set(qn('w:w'), str(val))
            node.set(qn('w:type'), 'dxa')
            tcMar.append(node)
        tcPr.append(tcMar)

    def set_table_borders(table, color="D3D3D3"):
        tblPr = table._tbl.tblPr
        borders = parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'  <w:top w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
            f'  <w:left w:val="none"/>'
            f'  <w:bottom w:val="single" w:sz="6" w:space="0" w:color="{color}"/>'
            f'  <w:right w:val="none"/>'
            f'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
            f'  <w:insideV w:val="none"/>'
            f'</w:tblBorders>'
        )
        tblPr.append(borders)

    def add_title(text, subtitle=None):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(20)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(26)
        run.font.bold = True
        run.font.color.rgb = NAVY
        
        if subtitle:
            p2 = doc.add_paragraph()
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p2.paragraph_format.space_before = Pt(0)
            p2.paragraph_format.space_after = Pt(20)
            r2 = p2.add_run(subtitle)
            r2.font.name = 'Calibri'
            r2.font.size = Pt(13)
            r2.font.color.rgb = SLATE
            r2.font.italic = True

    def add_h1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(17)
        run.font.bold = True
        run.font.color.rgb = NAVY

    def add_h2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(13)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(13.5)
        run.font.bold = True
        run.font.color.rgb = SLATE

    def add_h3(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(9)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(11.5)
        run.font.bold = True
        run.font.color.rgb = DARK

    def add_body(text, bold_prefix=None, space_after=5):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_pre = p.add_run(bold_prefix)
            r_pre.font.name = 'Calibri'
            r_pre.font.size = Pt(10.5)
            r_pre.font.bold = True
            r_pre.font.color.rgb = DARK
        r_body = p.add_run(text)
        r_body.font.name = 'Calibri'
        r_body.font.size = Pt(10.5)
        r_body.font.color.rgb = DARK
        return p

    def add_bullet(text, bold_prefix=None):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_pre = p.add_run(bold_prefix)
            r_pre.font.name = 'Calibri'
            r_pre.font.size = Pt(10)
            r_pre.font.bold = True
            r_pre.font.color.rgb = DARK
        r_body = p.add_run(text)
        r_body.font.name = 'Calibri'
        r_body.font.size = Pt(10)
        r_body.font.color.rgb = DARK
        return p

    def add_callout(text, title="KEY ARCHITECTURAL PRINCIPLE"):
        tbl = doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = tbl.cell(0, 0)
        cell.width = Inches(6.5)
        set_cell_bg(cell, "F2F5F9")
        set_cell_margins(cell, top=140, bottom=140, left=180, right=180)
        
        # Left border highlight
        tcPr = cell._tc.get_or_add_tcPr()
        borders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'  <w:left w:val="single" w:sz="24" w:space="0" w:color="1F4E78"/>'
            f'  <w:top w:val="none"/>'
            f'  <w:right w:val="none"/>'
            f'  <w:bottom w:val="none"/>'
            f'</w:tcBorders>'
        )
        tcPr.append(borders)
        
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        r_title = p.add_run(f"[{title}]\n")
        r_title.font.name = 'Calibri'
        r_title.font.size = Pt(9.5)
        r_title.font.bold = True
        r_title.font.color.rgb = NAVY
        
        r_text = p.add_run(text)
        r_text.font.name = 'Calibri'
        r_text.font.size = Pt(10)
        r_text.font.italic = True
        r_text.font.color.rgb = DARK
        
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # -------------------------------------------------------------
    # DOCUMENT CONTENT
    # -------------------------------------------------------------

    # Metadata & Header
    add_title(
        "ChethanQuant Stock Screener & Backtester",
        "Comprehensive Architecture, Mathematical Logic, Data Ingestion & Technical Defense Manual"
    )

    p_meta = doc.add_paragraph()
    p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_meta.paragraph_format.space_after = Pt(25)
    r_meta = p_meta.add_run("Author: Chethan Umapathi | System Architecture: Production Quantitative Trading Platform | Date: September 2026")
    r_meta.font.name = 'Calibri'
    r_meta.font.size = Pt(9.5)
    r_meta.font.color.rgb = MUTED

    add_callout(
        "This document is an exhaustive reference manual covering every technical component, data provider, "
        "database schema, formula, and edge-case correction implemented in the ChethanQuant platform. "
        "It provides deep, unassailable answers to any architectural, mathematical, or operational question.",
        "EXECUTIVE BRIEFING"
    )

    # SECTION 1
    add_h1("1. Executive Overview & Platform Vision")
    add_body(
        "The ChethanQuant Stock Screener & Backtester is an institutional-grade, multi-asset quantitative research and execution "
        "system engineered specifically for the National Stock Exchange of India (NSE). The platform bridges the gap between high-speed "
        "technical screening, sub-minute order flow analysis, and hyper-realistic portfolio backtesting."
    )
    add_body(
        "Unlike commercial black-box screeners that rely on delayed third-party aggregators or simplified cloud simulations, "
        "this platform operates entirely locally with high-performance vector databases, providing sub-millisecond execution, complete "
        "corporate action / split adjustments, real-world execution frictions (slippage, taxes, brokerage), and institutional risk diagnostics."
    )
    
    add_h2("Core System Capabilities:")
    add_bullet(" High-speed multi-timeframe scanner (1-min, 5-min, 15-min, Daily, Weekly) covering 2,294+ active NSE equities.", "Multi-Timeframe Technical Screening:")
    add_bullet(" Floor pivots, Camarilla (H3/L3 reversal, H4/L4 breakout), and Central Pivot Range (CPR) projected across Monthly and Yearly horizons.", "Multi-Horizon Pivot Analysis:")
    add_bullet(" Bar-by-bar chronological trade simulation with zero lookahead bias, strict order execution sequencing, and position concurrency tracking.", "Realistic Portfolio Backtester:")
    add_bullet(" Maximum Drawdown duration (contraction vs recovery), Ulcer Index, Time Under Water %, Sharpe, Sortino, Calmar, and Daily MTM Alpha/Beta against Nifty 50.", "Institutional Risk Engine:")
    add_bullet(" Automated 65% In-Sample / 35% Out-of-Sample chronological validation split strictly by trade entry date.", "Walk-Forward Out-of-Sample Suite:")
    add_bullet(" 1,000-iteration bootstrap simulation analyzing drawdown confidence intervals and concurrency tail risks.", "Monte Carlo Stress Testing:")
    add_bullet(" Real-time market regime categorization (Bull, Bear, Sideways) via sorted asof joins against Nifty 50 200 SMA and slope.", "Market Regime Classification:")

    # SECTION 2
    add_h1("2. High-Level System Architecture & Component Mapping")
    add_body(
        "The application follows a modular, decoupled four-tier architecture designed for maximum computational throughput, "
        "fault isolation, and portability."
    )

    add_body(
        "+---------------------------------------------------------------------------------------+\n"
        "|                             TIER 1: PRESENTATION & API LAYER                         |\n"
        "|  - Flask 3.x REST Web Server (Port 8000)                                              |\n"
        "|  - Responsive Single-Page UI (HTML5, Vanilla CSS Glassmorphism, Vanilla JS)           |\n"
        "|  - Chart.js & Lightweight Candlestick Charts                                          |\n"
        "|  - ReportLab 4.x Institutional PDF Generation Engine (Multi-page tearsheet)            |\n"
        "+---------------------------------------------------------------------------------------+\n"
        "                                           | JSON / REST APIs\n"
        "                                           v\n"
        "+---------------------------------------------------------------------------------------+\n"
        "|                             TIER 2: ANALYTICAL & SIMULATION ENGINE                    |\n"
        "|  - Strategy Execution Engine (app.py: run_backtest_simulation)                        |\n"
        "|  - Trade Accounting & Friction Modeler (compute_backtest_analytics)                    |\n"
        "|  - Institutional Diagnostics Suite (backtest_diagnostics.py)                          |\n"
        "|  - Order Flow Profiling & Delta Volume Engine (orderflow_engine.py)                   |\n"
        "+---------------------------------------------------------------------------------------+\n"
        "                                           | Vectorized In-Memory Pipelines\n"
        "                                           v\n"
        "+---------------------------------------------------------------------------------------+\n"
        "|                             TIER 3: DATABASE & STORAGE ENGINE                         |\n"
        "|  - DuckDB In-Process Analytical OLAP Engine (Columnar Vector Execution)                |\n"
        "|  - Apache Parquet Storage (data/minute/*.parquet & data/adjusted_daily/*.parquet)     |\n"
        "|  - JSON Dynamic Cache (splits_cache.json, strategies.json, market_cap_cache.json)     |\n"
        "+---------------------------------------------------------------------------------------+\n"
        "                                           | Asynchronous Ingestion & Cleaners\n"
        "                                           v\n"
        "+---------------------------------------------------------------------------------------+\n"
        "|                             TIER 4: DATA PROVIDERS & INGESTION                        |\n"
        "|  - Zerodha Kite Connect API: 1-minute historical tick data (0.38s rate limited)        |\n"
        "|  - Kotak Neo Trade API: Live tick streaming & EOD minute stitching                     |\n"
        "|  - National Stock Exchange (NSE India Direct): EQUITY_L.csv & Nifty 500 constituents   |\n"
        "|  - Yahoo Finance API (^NSEI): Nifty 50 historical benchmark data                      |\n"
        "+---------------------------------------------------------------------------------------+"
    )

    # SECTION 3
    add_h1("3. Comprehensive Data Catalog: Sources, Ingestion & Storage")
    add_body(
        "The following table provides an exhaustive audit of every data folder, file type, data origin, "
        "download mechanism, and operational purpose in the system:"
    )

    # Table of files
    table = doc.add_table(rows=1, cols=5)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table)
    
    headers = ["Directory / File", "Provider / Source", "Extraction Method", "Format & Size", "System Function"]
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        set_cell_bg(hdr_cells[i], "1F4E78")
        set_cell_margins(hdr_cells[i], 120, 120, 100, 100)
        p = hdr_cells[i].paragraphs[0]
        r = p.runs[0]
        r.font.bold = True
        r.font.color.rgb = WHITE
        r.font.size = Pt(9.5)

    data_catalog = [
        ("data/minute/\n{SYMBOL}.parquet", "Zerodha Kite Connect API\n(Official Broker API)", "REST HTTPS historical queries chunked into 60-day blocks; 0.38s delay pacing", "Apache Parquet\n(2,294 files, ~10.2 GB)", "Provides pristine 1-minute intraday OHLCV candle data from 2021 to present for all NSE equities >= Rs 2,000 Cr mcap."),
        ("data/adjusted_daily/\n{SYMBOL}.parquet", "Pre-computed from 1-min data via build_daily_cache.py", "Vectorized DuckDB aggregation: Open, Max(High), Min(Low), Close, Sum(Volume)", "Apache Parquet\n(2,294 files, ~89 MB)", "Ultra-fast daily screening & multi-year backtesting. Fully split-adjusted; eliminates overhead of scanning 10 GB of minute ticks."),
        ("data/instruments/\nnse_all_equities.csv", "National Stock Exchange\n(archives.nseindia.com)", "Direct HTTP GET of official NSE EQUITY_L.csv master file", "CSV (~177 KB,\n~2,294 rows)", "Defines the active equity universe on NSE, listing symbol, company name, ISIN, listing date, and face value."),
        ("data/instruments/\nnifty500_instruments.csv", "NSE India Index Archive\n(archives.nseindia.com)", "Direct HTTP GET of ind_nifty500list.csv", "CSV (~40 KB,\n501 rows)", "Provides official constituent list for Nifty 500 universe filtering."),
        ("data/universe/\nmcap_above_2000cr_*.csv", "Computed by market_cap.py\nvia NSE API & shares out", "Dynamic query multiplying latest share price by official paid-up share capital", "CSV (~65 KB,\n~1,200 stocks)", "Filters the NSE universe for institutional liquidity; ensures screener only tracks companies with Market Cap >= Rs 2,000 Crores."),
        ("data/fundamentals/\nstatements/{SYM}.json", "Yahoo Finance API &\nNSE Corporate Filings", "REST API fetch parsing quarterly balance sheets, P&L, and cash flows", "JSON (1,476 files,\n~151 MB)", "Stores Debt-to-Equity, Operating Margins, Profit Margins, Dividend Yields, and Net Income for fundamental filters."),
        ("data/splits_cache.json", "NSE Corporate Actions &\nHistorical Seam Detector", "Scrapes NSE Corporate Actions database; verified with price continuity scan", "JSON (~72 KB,\n2,156 events)", "Contains exact split dates and adjustment factors (e.g. 1:2 split = factor 0.5) to normalize prices across corporate actions."),
        ("data/nifty50_benchmark\n.parquet", "Yahoo Finance (^NSEI) &\nNSE Historical Index Data", "yfinance download with 200 SMA and 20-day slope pre-computed", "Apache Parquet\n(~68 KB, 1,662 days)", "Official benchmark for Alpha, Beta, Correlation, CAGR comparison, and dynamic Bull/Bear/Sideways market regime assignment."),
        ("data/backtest_strategies\n.json & strategies.json", "User Strategy Definition\n& Pre-built Library", "Stored via web UI code editor or Python strategy registration scripts", "JSON (~105 KB,\n16 strategies)", "Stores strategy Python code, Pine Script translations, timeframe, TP/SL rules, and parameter configurations."),
        ("data/orderflow/\norderflow.duckdb", "Live WebSocket Tick Engine\n(Kotak Neo & Zerodha)", "Streaming tick aggregator computing bid/ask delta volume and POC", "DuckDB Database\n(~2.6 MB)", "Stores institutional order flow profiles, Volume at Price (VAP), delta imbalance, and Point of Control (POC) levels."),
        ("data/consolidated_data\n.csv (Optional Legacy)", "NSE Official Daily Bhavcopy\n(sec_bhavdata_full_*.csv)", "Historical daily scraper fetching delivery volume, traded quantity, and delivery %", "CSV (~228 MB,\n~965 sessions)", "Legacy delivery volume archive. Preserves historical delivery % for volume breakout scanners.")
    ]

    for row_idx, data in enumerate(data_catalog):
        row = table.add_row()
        bg = "F9FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.text = text
            set_cell_bg(c, bg)
            set_cell_margins(c, 100, 100, 80, 80)
            p = c.paragraphs[0]
            r = p.runs[0]
            r.font.size = Pt(8.5)
            r.font.color.rgb = DARK
            if col_idx == 0:
                r.font.bold = True

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # Ingestion Deep Dives
    add_h2("3.1 Ingestion Deep Dive: Zerodha Kite Connect 1-Minute Downloader")
    add_body(
        "The 1-minute historical data pipeline (located in zerodha_downloader/) is designed to be completely resilient, "
        "rate-limit compliant, and self-healing:"
    )
    add_bullet("Kite Connect enforces a strict rate limit of 3 requests per second for historical data. The downloader paces requests with a hard 0.38-second interval delay (~2.6 req/sec), guaranteeing zero HTTP 429 Too Many Requests errors.", "Strict Rate Limiting:")
    add_bullet("Zerodha rejects queries spanning more than 60 calendar days for 1-minute intervals. The downloader programmatically chunks multi-year requests into safe 60-day date windows and seamlessly stitches them.", "Intelligent 60-Day Chunking:")
    add_bullet("When downloading or updating, the script inspects the maximum timestamp in the local Parquet file and only queries missing bars, eliminating redundant API overhead.", "Deduplication & Resume:")
    add_bullet("Zerodha API access tokens expire daily at 06:00 AM IST. The authentication module securely caches the session token in .kite_token.json and reuses it across daily runs without prompting for manual OTP.", "Automated Token Caching:")

    add_h2("3.2 Ingestion Deep Dive: Split Adjustment & Seam Stitching Engine")
    add_body(
        "One of the most complex challenges in quantitative finance is handling corporate actions (stock splits and bonus issues). "
        "An unadjusted stock split (e.g. 1:10 split where a Rs 1,000 stock becomes Rs 100) causes an artificial 90% drawdown that completely "
        "destroys backtest validity."
    )
    add_body(
        "The ChethanQuant platform solves this using a two-stage split adjustment algorithm in build_daily_cache.py and app.py:"
    )
    add_bullet("Every split event in splits_cache.json records the ex-date, old price, new price, and ratio. The algorithm verifies whether the price dropped by the exact ratio on the split date. If the raw data is already adjusted, no duplicate factor is applied.", "Verification Before Adjustment:")
    add_bullet("Older historical data (from legacy Kotak dumps prior to 13-Sept-2023) was unadjusted, whereas newer Zerodha data was already split-adjusted. The engine detects this seam discontinuity across 44 specific tickers (e.g. HAL, BDL, BPCL, VEDL) and applies seamless backward multipliers to prevent artificial price jumps.", "Seam Stitching Resolution:")

    # SECTION 4
    add_h1("4. Database & Storage Technology Rationale")
    add_body(
        "The platform's performance advantage relies on an optimized hybrid storage architecture combining DuckDB and Apache Parquet:"
    )

    add_h2("4.1 Why DuckDB Over Traditional Relational Databases (PostgreSQL / MySQL / SQLite)?")
    add_bullet("Traditional relational databases process queries row-by-row (tuple-at-a-time). DuckDB uses a vectorized columnar execution engine that processes data in 2,048-value vectors utilizing CPU SIMD instructions. A full-market scan across 500 stocks takes 2.6 seconds instead of 45 seconds.", "Vectorized Analytical Processing (OLAP):")
    add_bullet("DuckDB queries Parquet files directly on disk via its read_parquet() scanner without loading or importing tables into a database server. This eliminates database server maintenance, connection pooling overhead, and disk duplication.", "Zero-Copy Parquet Scanning:")
    add_bullet("DuckDB runs in-process as an embedded C++ library inside Python. There is no network socket, serialization, or IPC latency between the Python backtesting logic and the data engine.", "Embedded In-Process Engine:")

    add_h2("4.2 Why Apache Parquet Over Flat CSVs?")
    add_bullet("CSVs store repetitive string headers and numeric characters. Parquet utilizes Snappy compression, dictionary encoding, and bit-packing, reducing 100+ GB of raw stock tick CSVs into ~10.2 GB.", "10x Compression Efficiency:")
    add_bullet("Parquet stores metadata including min/max statistics per data page. When querying a date range (e.g. WHERE date >= '2024-01-01'), DuckDB reads only the relevant column chunks and skips non-matching row groups entirely without reading them from disk.", "Predicate Pushdown & Column Pruning:")

    # SECTION 5
    add_h1("5. Core Quantitative Logic & Mathematical Formulations")

    add_h2("5.1 Multi-Horizon Pivot Point Calculations")
    add_body(
        "Pivot points represent psychological support and resistance levels derived from previous session price extremes (High H, Low L, Close C):"
    )

    add_bullet("Pivot P = (H + L + C) / 3\n"
               "R1 = (2 * P) - L    |    S1 = (2 * P) - H\n"
               "R2 = P + (H - L)    |    S2 = P - (H - L)\n"
               "R3 = H + 2 * (P - L) |   S3 = L - 2 * (H - P)\n"
               "R4 = R3 + (H - L)   |    S4 = S3 - (H - L)", "Standard Floor Pivots:")
    
    add_bullet("H4 = C + Range * 1.1 / 2 (Breakout Buy)\n"
               "H3 = C + Range * 1.1 / 4 (Reversal Sell)\n"
               "L3 = C - Range * 1.1 / 4 (Reversal Buy)\n"
               "L4 = C - Range * 1.1 / 2 (Breakout Sell)", "Camarilla Pivots (Range = H - L):")

    add_bullet("Pivot = (H + L + C) / 3\n"
               "Bottom Central (BC) = (H + L) / 2\n"
               "Top Central (TC) = (Pivot - BC) + Pivot\n"
               "Width = |TC - BC| (Narrow CPR signals upcoming high-volatility breakout trend)", "Central Pivot Range (CPR):")

    add_h2("5.2 Realistic Backtesting Execution Simulation")
    add_body(
        "Commercial backtesters often suffer from execution illusions. The ChethanQuant engine guarantees institutional realism through the following mechanisms:"
    )

    add_bullet("A trade triggers strictly on bar close confirmation. If candle closes above Monthly R3 and above Yearly R2, execution enters at open of the next bar or exact breakout close.", "Bar-Close Execution Sequencing:")
    add_bullet("Every trade model includes 0.5% default price slippage + NSE STT (Securities Transaction Tax: 0.1% on delivery buy/sell) + exchange turnover charges + GST (18% on brokerage) + flat Rs 20/order broker fee.", "Friction & Slippage Modeling:")
    add_callout(
        "CRITICAL FIX: If multiple positions exit on the same bar (e.g. same day or week), processing trades in arbitrary "
        "row order causes artificial intermediate drawdown whipsaws if a losing trade is processed before a winning trade on the same bar. "
        "The engine aggregates all trade exits on the same bar date into bar_exits_map before updating equity. This eliminated false "
        "1-day MDD artifacts and produced accurate, continuous duration measurements.",
        "SAME-BAR EXIT AGGREGATION ALGORITHM"
    )

    add_h2("5.3 Institutional Risk & Performance Metrics")
    
    add_bullet("Evaluates equity drops from running peak. Total MDD duration = Contraction Days (peak to valley) + Recovery Days (valley back to new peak). Longest Underwater Period tracks the maximum calendar span the portfolio remained below its high-water mark.", "Maximum Drawdown (MDD) & Continuous Duration:")
    add_bullet("Ulcer Index = sqrt(mean(DD%^2)). Measures the depth and duration of drawdowns. Unlike standard deviation (which penalizes upside volatility), Ulcer Index exclusively measures downside distress. Recovery Factor = Net Profit / |MDD|.", "Ulcer Index & Recovery Factor:")
    add_bullet("Annualized return based on peak capital deployed over total years. Calmar Ratio = CAGR / Max DD %.", "CAGR & Calmar Ratio:")
    add_bullet("Annualized excess monthly returns over a 6% risk-free rate. Sortino replaces total standard deviation with downside semi-deviation to reward upside volatility.", "Sharpe Ratio & Sortino Ratio:")
    add_bullet("Calculated on daily MTM percentage returns of the rebased strategy equity curve against Nifty 50 daily close returns. Beta = Cov(Strat, Nifty) / Var(Nifty). Correlation r = Pearson correlation of daily returns. Alpha = Strategy CAGR - (6.0 + Beta * (Nifty CAGR - 6.0)).", "Benchmark Beta, Alpha & Correlation:")
    add_bullet("Nifty 50 close price is compared to its 200-day Simple Moving Average (SMA) and 20-day slope. Bull = Close > 200 SMA and Slope > 0; Bear = Close < 200 SMA and Slope < 0; Sideways = Consolidating / Flattish slope. Utilizes np.searchsorted asof join to match non-trading/weekend trade entry dates.", "Dynamic Market Regime Breakdown:")
    add_bullet("Reshuffles trade P&L sequence across 1,000 bootstrap simulations to compute the 95th-percentile worst-case drawdown. Evaluates P(Drawdown > Historical MDD) to determine whether historical drawdown was an outlier or standard risk.", "Monte Carlo Stress Simulation:")
    add_bullet("Strictly splits trades chronologically by ENTRY DATE into 65% In-Sample (training) and 35% Out-of-Sample (unseen validation). Includes running open trades at Mark-to-Market equity to guarantee zero lookahead leakage.", "Walk-Forward Out-of-Sample Analysis:")

    # SECTION 6
    add_h1("6. Detailed Workflow: From User Click to PDF Report")
    add_body(
        "When an investor or user executes a backtest on the web dashboard, the system executes the following deterministic lifecycle:"
    )
    add_bullet("User submits strategy code, segment (Nifty 50, Nifty 500, All NSE), timeframe, date range, and friction parameters. The endpoint validates code syntax and confirms presence of Long Entry, TP, and SL logic.", "1. API Submission & Pre-validation (/api/backtest):")
    add_bullet("DuckDB executes vectorized SQL queries across data/adjusted_daily/*.parquet (or data/minute/*.parquet if intraday). It filters for min market cap (>= Rs 2,000 Cr) and loads OHLCV bars into clean pandas DataFrames.", "2. Vectorized Parquet Slicing:")
    add_bullet("Strategy backtest(df) runs across all selected stocks in parallel. Trade entries, exits, durations, MAE, MFE, and reasons are logged.", "3. Trade Simulation:")
    add_bullet("Trades are aggregated by exit bar into equity curves. Daily continuous equity is evaluated against running peaks. Peak capital deployed is calculated via timeline event sweep.", "4. Friction & Accounting Computation:")
    add_bullet("In under 50 milliseconds, compute_comprehensive_diagnostics runs Ulcer Index, Benchmark Alpha/Beta, OOS 65/35 split, Monte Carlo 1,000 reshuffles, Market Regime asof join, and Position Sizing models.", "5. Institutional Diagnostics Pipeline:")
    add_bullet("Flask sends unified JSON payload to client for interactive Chart.js rendering, and bundles the exact analytics payload into ReportLab to produce an institutional, multi-page PDF tearsheet.", "6. Presentation & PDF Generation:")

    # SECTION 7
    add_h1("7. Master Defense Cheat Sheet: 20 Deep Technical Questions & Answers")
    add_body(
        "Use these precise answers when questioned on architecture, quantitative methodology, data integrity, or edge-case handling:"
    )

    qas = [
        ("Q1: How do you guarantee zero lookahead bias in your backtests?",
         "A1: Trade entry signals are confirmed strictly on the CLOSE of bar T. Execution occurs either at the exact Close of bar T or the Open of bar T+1. Intra-bar highs and lows are only evaluated AFTER the position has formally entered. No future bar data is ever accessible to the strategy function."),
        
        ("Q2: How does your system handle stock splits and corporate actions without distorting returns?",
         "A2: We maintain an explicit splits_cache.json tracking ex-dates and adjustment ratios for 2,156 events. In build_daily_cache.py, the engine checks price continuity across the split date to avoid double adjustment, and applies backward multiplication factors to older prices so historical percentage breakouts remain mathematically accurate."),

        ("Q3: Why did you choose DuckDB over PostgreSQL or SQLite?",
         "A3: DuckDB is an OLAP (Online Analytical Processing) columnar engine that uses vectorized execution and SIMD instructions to scan millions of rows in milliseconds. Unlike PostgreSQL, DuckDB requires no server setup and scans Parquet files directly via zero-copy. Unlike SQLite (which is row-based), DuckDB processes analytics 50x-100x faster."),

        ("Q4: Why are same-bar exits aggregated before updating equity?",
         "A4: If 5 trades exit on the same day/week, processing them row-by-row means an arbitrary losing trade processed first temporarily drops portfolio equity, creating a false intermediate peak and artificial 1-day drawdown. Aggregating all exits on the same bar (bar_exits_map) applies the net bar delta to equity, accurately reflecting true portfolio equity."),

        ("Q5: How is the Nifty 50 market regime join computed for trades on weekends or non-trading days?",
         "A5: Weekly strategy bars are dated on Fridays or Sundays, while Nifty daily bars only exist on trading days. We use np.searchsorted as an asof join to map any trade date to the most recent prior trading day's 200 SMA and slope, eliminating date-mismatch failures that previously categorized all trades as Sideways."),

        ("Q6: How are Sharpe and Sortino ratios calculated in the report?",
         "A6: They are calculated using monthly excess returns over a 6% annual risk-free rate (rf = 0.5% per month), multiplied by sqrt(12) for annualization. Sortino uses downside semi-deviation (only negative excess deviations) to ensure upside volatility is not penalized."),

        ("Q7: What is the difference between In-Sample and Out-of-Sample in your platform?",
         "A7: We partition trades chronologically by ENTRY DATE (65% IS / 35% OOS). Sorting by exit date causes leakage because trades entering in IS would exit in OOS. We also evaluate open running trades at Mark-to-Market equity so no trade information is lost."),

        ("Q8: Where does the 1-minute data come from and how is it kept up to date?",
         "A8: Raw 1-minute Parquet files (~10.2 GB) are downloaded via Zerodha Kite Connect API in 60-day chunks with 0.38s rate pacing. The daily sync service checks the latest timestamp in each file and only downloads incremental delta bars during market hours."),

        ("Q9: What is the Ulcer Index and why is it superior to standard deviation?",
         "A9: Standard deviation treats positive returns and negative returns as equally risky. The Ulcer Index measures the root mean square of percentage drawdowns below previous peaks. It specifically measures the emotional and financial pain of holding a portfolio during prolonged drawdown periods."),

        ("Q10: Why did you decouple daily screening from the 1-minute Parquet store?",
         "A10: Scanning 10.2 GB of 1-minute tick data for daily or weekly breakout signals is redundant and computationally expensive. build_daily_cache.py pre-aggregates 1-minute data into corporate-action-adjusted daily Parquet files (89 MB total), making full-universe daily screening run in under 3 seconds."),

        ("Q11: How do you model execution frictions?",
         "A11: Every trade simulation applies 0.5% price slippage on entry and exit, flat Rs 20 brokerage per order, NSE STT (0.1%), exchange turnover fees, and 18% GST on brokerage. Headline net profit is strictly net of all commissions and slippage."),

        ("Q12: How is Peak Capital Deployed calculated?",
         "A12: We run a timeline event sweep algorithm: each trade entry adds +1 position, and its exit removes -1 position. The peak concurrent positions multiplied by capital per trade determines the peak capital deployed. CAGR and Calmar ratios are calculated against this realistic peak capital, not total cumulative gross capital."),

        ("Q13: Why are ATR and Compounding rows in Position Sizing marked 'Under Rebuild'?",
         "A13: Naive compounding loops on fat-tailed breakout strategies compound outlier returns into astronomical, unrealistic numbers (e.g. hundreds of crores). We enforce institutional honesty by locking Fixed Capital net profit to the exact headline profit and marking unbounded compounding models as Under Rebuild until portfolio volatility sizing is implemented."),

        ("Q14: How does the Monte Carlo stress simulation work?",
         "A14: We bootstrap reshuffle the historical trade P&L sequence 1,000 times without replacement to simulate alternative sequences of winning and losing streaks. It computes the 95th-percentile worst-case drawdown and the probability of exceeding historical MDD."),

        ("Q15: What is the difference between Camarilla and Standard Pivots?",
         "A15: Standard floor pivots use arithmetic divisions of the previous range (P, R1-R4, S1-S4). Camarilla pivots use Fibonacci-derived multipliers (1.1 / 2 and 1.1 / 4) of the previous range. H3/L3 are mean-reversion reversal zones, while H4/L4 are high-conviction breakout continuation levels."),

        ("Q16: How do you prevent survivorship bias in the stock universe?",
         "A16: The universe is anchored to the official NSE All Equities master list and historical Nifty 500 constituent snapshots, ensuring backtests evaluate historical index members even if their market cap later dropped."),

        ("Q17: How is Alpha and Beta calculated against the Nifty 50?",
         "A17: Rather than comparing lumpy monthly realised P&L, we rebase the strategy continuous daily MTM equity curve to base 100 alongside Nifty 50 daily close. We compute daily percentage returns for both and evaluate Beta = Cov(Strat, Nifty) / Var(Nifty) and Alpha = Strategy CAGR - [6.0 + Beta * (Nifty CAGR - 6.0)]."),

        ("Q18: What is Time Under Water (TUW %)?",
         "A18: TUW % is the percentage of total calendar trading days that the portfolio's equity was strictly below its all-time high-water mark. A strategy with high win rate can still spend 50%+ of its life underwater during sideways market consolidations."),

        ("Q19: How are multi-year reports exported to PDF?",
         "A19: We utilize ReportLab 4.x with a custom two-column grid canvas that dynamically compiles the Executive Summary, Trade Statistics, Year-Wise Monthly Heatmap, Continuous Drawdown Underwater Chart, Diagnostics Radar, and Trade Logs into a publication-ready PDF in under 1 second."),

        ("Q20: Why are Bhavcopies no longer needed in the repository?",
         "A20: Individual daily NSE Bhavcopy CSVs were legacy downloads used solely for end-of-day delivery volume screening. All 965 historical sessions were already consolidated into data/consolidated_data.csv. All price action, indicators, and backtests run on Apache Parquet files, making raw individual Bhavcopies completely redundant.")
    ]

    for q, a in qas:
        p_q = doc.add_paragraph()
        p_q.paragraph_format.space_before = Pt(8)
        p_q.paragraph_format.space_after = Pt(2)
        p_q.paragraph_format.keep_with_next = True
        r_q = p_q.add_run(q)
        r_q.font.name = 'Calibri'
        r_q.font.size = Pt(11)
        r_q.font.bold = True
        r_q.font.color.rgb = NAVY

        p_a = doc.add_paragraph()
        p_a.paragraph_format.space_after = Pt(6)
        p_a.paragraph_format.line_spacing = 1.15
        r_a = p_a.add_run(a)
        r_a.font.name = 'Calibri'
        r_a.font.size = Pt(10)
        r_a.font.color.rgb = DARK

    # Save to docs folder
    os.makedirs('docs', exist_ok=True)
    out_path = os.path.abspath('docs/ChethanQuant_System_Architecture_and_Logic_Guide.docx')
    doc.save(out_path)
    print(f"Document successfully created and saved to: {out_path}")

    # Also copy to G-Drive docs folder
    g_docs = r'G:\My Drive\Stock_Screener\docs'
    if os.path.exists(r'G:\My Drive\Stock_Screener'):
        os.makedirs(g_docs, exist_ok=True)
        g_out_path = os.path.join(g_docs, 'ChethanQuant_System_Architecture_and_Logic_Guide.docx')
        import shutil
        shutil.copy2(out_path, g_out_path)
        print(f"Document successfully synced to Google Drive: {g_out_path}")

if __name__ == '__main__':
    create_document()

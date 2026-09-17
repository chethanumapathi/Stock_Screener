"""
NSE Stock Fundamentals Downloader
==================================
Fetches, normalizes, and stores:
1. Key Financial Ratios (P/E, P/B, ROE, ROA, Debt/Equity, Margins, Dividend Yield, Market Cap)
2. Quarterly P&L (Income Statement)
3. Yearly P&L (Income Statement)
4. Yearly Balance Sheet
5. Yearly Cash Flow Statements

Data is cached locally in:
- data/fundamentals/ratios_summary.json (Aggregated table for fast screener filtering)
- data/fundamentals/ratios_summary.csv  (CSV version for analytics/DuckDB query)
- data/fundamentals/statements/{SYMBOL}.json (Deep time-series financial statements per stock)
"""

import os
import sys
import time
import json
import argparse
import logging
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("download_fundamentals")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
FUNDAMENTALS_DIR = os.path.join(DATA_DIR, 'fundamentals')
STATEMENTS_DIR = os.path.join(FUNDAMENTALS_DIR, 'statements')
RATIOS_SUMMARY_JSON = os.path.join(FUNDAMENTALS_DIR, 'ratios_summary.json')
RATIOS_SUMMARY_CSV = os.path.join(FUNDAMENTALS_DIR, 'ratios_summary.csv')
NIFTY50_FILE = os.path.join(DATA_DIR, 'nifty50.csv')
NIFTY500_FILE = os.path.join(DATA_DIR, 'nifty500.csv')

# Ensure directories exist
os.makedirs(FUNDAMENTALS_DIR, exist_ok=True)
os.makedirs(STATEMENTS_DIR, exist_ok=True)


def _safe_float(val, precision=2, scale=1.0):
    """Safely converts and scales values to float, rounding to given precision."""
    if val is None or pd.isna(val):
        return None
    try:
        f = float(val) * scale
        return round(f, precision) if precision is not None else f
    except (ValueError, TypeError):
        return None


def _clean_df_for_export(df: pd.DataFrame) -> dict:
    """
    Transforms a yfinance financial statement DataFrame:
    - Transposes so dates are records (rows)
    - Replaces NaNs with None
    - Converts values into ₹ Crores where appropriate
    - Returns a dict structured for clean JSON serialization and UI rendering
    """
    if df is None or df.empty:
        return {"dates": [], "metrics": {}, "records": []}

    try:
        # Dates are columns in yfinance statements, line items are index
        # Format date column headers to YYYY-MM-DD
        date_cols = []
        for col in df.columns:
            if hasattr(col, 'strftime'):
                date_cols.append(col.strftime('%Y-%m-%d'))
            else:
                date_cols.append(str(col)[:10])

        df_copy = df.copy()
        df_copy.columns = date_cols

        # Build records list sorted newest to oldest date
        records = []
        for d in date_cols:
            rec = {"date": d}
            for metric in df_copy.index:
                val = df_copy.loc[metric, d]
                if pd.isna(val) or val is None:
                    rec[metric] = None
                else:
                    try:
                        # Raw numbers are in actual rupees; convert to Crores (÷ 1e7) for financial statement items
                        # Note: Per-share items (EPS) or ratios should not be divided by 1e7
                        m_low = str(metric).lower()
                        if "eps" in m_low or "per share" in m_low or "rate" in m_low or "ratio" in m_low or "shares" in m_low:
                            rec[metric] = round(float(val), 2)
                        else:
                            rec[metric] = round(float(val) / 1e7, 2)  # In ₹ Cr
                    except (ValueError, TypeError):
                        rec[metric] = str(val)
            records.append(rec)

        # Build metrics dictionary: metric_name -> list of values across dates
        metrics_dict = {}
        for metric in df_copy.index:
            vals = {}
            for d in date_cols:
                v = df_copy.loc[metric, d]
                if pd.isna(v) or v is None:
                    vals[d] = None
                else:
                    try:
                        m_low = str(metric).lower()
                        if "eps" in m_low or "per share" in m_low or "rate" in m_low or "ratio" in m_low or "shares" in m_low:
                            vals[d] = round(float(v), 2)
                        else:
                            vals[d] = round(float(v) / 1e7, 2)
                    except (ValueError, TypeError):
                        vals[d] = str(v)
            metrics_dict[metric] = vals

        return {
            "dates": date_cols,
            "metrics": metrics_dict,
            "records": records
        }
    except Exception as e:
        logger.warning(f"Error structuring statement DataFrame: {e}")
        return {"dates": [], "metrics": {}, "records": []}


def fetch_fundamentals_for_symbol(symbol: str, timeout: int = 15) -> dict:
    """
    Downloads fundamental ratios and detailed financial statements for a single stock ticker.
    Supports symbols with or without '.NS' suffix.
    """
    clean_symbol = symbol.upper().replace('.NS', '').strip()
    ticker_sym = f"{clean_symbol}.NS"
    ticker = yf.Ticker(ticker_sym)

    # 1. Fetch Company Info & Ratios
    info = {}
    try:
        info = ticker.info or {}
    except Exception as e:
        logger.debug(f"[{clean_symbol}] Warning fetching info: {e}")

    # Fallback to fast_info for market cap if info is sparse
    mcap = info.get("marketCap")
    if not mcap and hasattr(ticker, 'fast_info'):
        try:
            mcap = ticker.fast_info.get("marketCap")
        except Exception:
            pass

    market_cap_cr = _safe_float(mcap, precision=2, scale=1e-7)

    # Normalize debt to equity (yfinance provides D/E as a percentage e.g. 10.21% = 0.10)
    raw_de = info.get("debtToEquity")
    de_ratio = None
    if raw_de is not None:
        try:
            de_val = float(raw_de)
            de_ratio = round(de_val / 100.0, 2) if de_val > 5.0 else round(de_val, 2)
        except (ValueError, TypeError):
            de_ratio = None

    # Normalize dividend yield (yfinance provides either decimal 0.0289 or percentage 2.89)
    raw_div = info.get("dividendYield")
    div_yield_pct = None
    if raw_div is not None:
        try:
            div_val = float(raw_div)
            div_yield_pct = round(div_val, 2) if div_val > 0.5 else round(div_val * 100.0, 2)
        except (ValueError, TypeError):
            div_yield_pct = None

    # Compile unified ratio dictionary
    ratios = {
        "symbol": clean_symbol,
        "companyName": info.get("longName") or info.get("shortName") or clean_symbol,
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "marketCapCr": market_cap_cr,
        "pe": _safe_float(info.get("trailingPE")),
        "forwardPE": _safe_float(info.get("forwardPE")),
        "pb": _safe_float(info.get("priceToBook")),
        "roe": _safe_float(info.get("returnOnEquity"), precision=2, scale=100.0),       # %
        "roa": _safe_float(info.get("returnOnAssets"), precision=2, scale=100.0),       # %
        "debtToEquity": de_ratio,
        "currentRatio": _safe_float(info.get("currentRatio")),
        "quickRatio": _safe_float(info.get("quickRatio")),
        "operatingMargin": _safe_float(info.get("operatingMargins"), precision=2, scale=100.0), # %
        "profitMargin": _safe_float(info.get("profitMargins"), precision=2, scale=100.0),       # %
        "dividendYield": div_yield_pct,                                                         # %
        "trailingEps": _safe_float(info.get("trailingEps")),
        "forwardEps": _safe_float(info.get("forwardEps")),
        "pegRatio": _safe_float(info.get("pegRatio")),
        "quarterlyEarningsGrowth": _safe_float(info.get("earningsQuarterlyGrowth"), precision=2, scale=100.0),
        "quarterlyRevenueGrowth": _safe_float(info.get("revenueGrowth"), precision=2, scale=100.0),
        "bookValue": _safe_float(info.get("bookValue")),
        "currency": info.get("currency", "INR"),
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # 2. Fetch Statements
    # Quarterly P&L (Income Statement)
    q_pnl = {}
    try:
        df_q_pnl = ticker.quarterly_financials
        q_pnl = _clean_df_for_export(df_q_pnl)
    except Exception as e:
        logger.debug(f"[{clean_symbol}] Quarterly financials fetch error: {e}")

    # Yearly P&L (Income Statement)
    y_pnl = {}
    try:
        df_y_pnl = ticker.financials
        y_pnl = _clean_df_for_export(df_y_pnl)
    except Exception as e:
        logger.debug(f"[{clean_symbol}] Yearly financials fetch error: {e}")

    # Yearly Balance Sheet
    y_bs = {}
    try:
        df_y_bs = ticker.balance_sheet
        y_bs = _clean_df_for_export(df_y_bs)
    except Exception as e:
        logger.debug(f"[{clean_symbol}] Yearly balance sheet fetch error: {e}")

    # Quarterly Balance Sheet
    q_bs = {}
    try:
        df_q_bs = ticker.quarterly_balance_sheet
        q_bs = _clean_df_for_export(df_q_bs)
    except Exception as e:
        logger.debug(f"[{clean_symbol}] Quarterly balance sheet fetch error: {e}")

    # Cash Flows
    y_cf = {}
    try:
        df_y_cf = ticker.cashflow
        y_cf = _clean_df_for_export(df_y_cf)
    except Exception as e:
        logger.debug(f"[{clean_symbol}] Cash flow fetch error: {e}")

    stock_data = {
        "symbol": clean_symbol,
        "ratios": ratios,
        "quarterly_pnl": q_pnl,
        "yearly_pnl": y_pnl,
        "yearly_balance_sheet": y_bs,
        "quarterly_balance_sheet": q_bs,
        "yearly_cash_flow": y_cf,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    return stock_data


def save_stock_statement(symbol: str, data: dict):
    """Saves per-stock deep financial statements to JSON."""
    clean_symbol = symbol.upper().replace('.NS', '').strip()
    file_path = os.path.join(STATEMENTS_DIR, f"{clean_symbol}.json")
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving statement JSON for {clean_symbol}: {e}")


def load_stock_statement(symbol: str) -> dict:
    """Loads per-stock deep financial statements from local JSON cache."""
    clean_symbol = symbol.upper().replace('.NS', '').strip()
    file_path = os.path.join(STATEMENTS_DIR, f"{clean_symbol}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading statement for {clean_symbol}: {e}")
    return {}


def load_all_ratios_summary() -> dict:
    """Loads the compiled ratios dictionary (symbol -> ratios dict)."""
    if os.path.exists(RATIOS_SUMMARY_JSON):
        try:
            with open(RATIOS_SUMMARY_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {RATIOS_SUMMARY_JSON}: {e}")
    return {}


def save_all_ratios_summary(summary_dict: dict):
    """Saves compiled ratios to both JSON and CSV for versatile screener joins."""
    try:
        with open(RATIOS_SUMMARY_JSON, 'w', encoding='utf-8') as f:
            json.dump(summary_dict, f, indent=2)

        # Also write CSV version
        records = list(summary_dict.values())
        if records:
            df = pd.DataFrame(records)
            df.to_csv(RATIOS_SUMMARY_CSV, index=False)
    except Exception as e:
        logger.error(f"Error saving ratios summary: {e}")


def download_fundamentals_for_symbol(symbol: str, force: bool = False, max_age_days: int = 7) -> dict:
    """
    Fetches and caches fundamentals for a single symbol.
    Skips if existing cache is younger than max_age_days, unless force=True.
    """
    clean_symbol = symbol.upper().replace('.NS', '').strip()
    existing_summary = load_all_ratios_summary()

    if not force and clean_symbol in existing_summary:
        last_updated_str = existing_summary[clean_symbol].get("lastUpdated")
        if last_updated_str:
            try:
                last_dt = datetime.strptime(last_updated_str[:10], "%Y-%m-%d")
                if (datetime.now() - last_dt).days < max_age_days:
                    # Cache is fresh
                    stmt = load_stock_statement(clean_symbol)
                    if stmt:
                        return stmt
            except Exception:
                pass

    logger.info(f"Downloading fundamentals for {clean_symbol}...")
    stock_data = fetch_fundamentals_for_symbol(clean_symbol)
    
    # Save individual statement
    save_stock_statement(clean_symbol, stock_data)

    # Update summary table
    if stock_data.get("ratios"):
        existing_summary[clean_symbol] = stock_data["ratios"]
        save_all_ratios_summary(existing_summary)

    return stock_data


def download_fundamentals_batch(symbols: list, force: bool = False, delay: float = 0.35, progress_callback=None) -> dict:
    """
    Downloads fundamentals for a batch of symbols with polite rate limiting.
    Calls progress_callback(current, total, symbol, status) if provided.
    """
    symbols = [s.upper().replace('.NS', '').strip() for s in symbols if s and str(s).strip()]
    total = len(symbols)
    logger.info(f"Starting fundamentals batch download for {total} stocks (delay={delay}s)...")

    summary_cache = load_all_ratios_summary()
    success_count = 0
    fail_count = 0

    for i, sym in enumerate(symbols):
        try:
            if not force and sym in summary_cache:
                last_up = summary_cache[sym].get("lastUpdated")
                if last_up:
                    try:
                        last_dt = datetime.strptime(last_up[:10], "%Y-%m-%d")
                        if (datetime.now() - last_dt).days < 7 and os.path.exists(os.path.join(STATEMENTS_DIR, f"{sym}.json")):
                            if progress_callback:
                                progress_callback(i + 1, total, sym, "cached")
                            continue
                    except Exception:
                        pass

            data = fetch_fundamentals_for_symbol(sym)
            save_stock_statement(sym, data)
            if data.get("ratios"):
                summary_cache[sym] = data["ratios"]
            success_count += 1

            if progress_callback:
                progress_callback(i + 1, total, sym, "success")
        except Exception as e:
            logger.error(f"Failed to fetch {sym}: {e}")
            fail_count += 1
            if progress_callback:
                progress_callback(i + 1, total, sym, f"error: {e}")

        # Save summary intermittently every 10 stocks or at the end
        if (i + 1) % 10 == 0 or (i + 1) == total:
            save_all_ratios_summary(summary_cache)

        if delay > 0 and i < total - 1:
            time.sleep(delay)

    save_all_ratios_summary(summary_cache)
    logger.info(f"Fundamentals batch download finished: {success_count} updated, {fail_count} failed, total {total}.")
    return summary_cache


def get_symbols_for_segment(segment: str = 'nifty50') -> list:
    """
    Retrieves list of symbols for given segment:
    - 'nifty50': 50 stocks from nifty50.csv
    - 'nifty500': 500 stocks from nifty500.csv
    - 'all' / 'universe' / 'parquet': ALL ~2,294 stocks from Zerodha Parquet library or local database
    """
    segment = segment.lower().strip()
    if segment == 'nifty50' and os.path.exists(NIFTY50_FILE):
        try:
            df = pd.read_csv(NIFTY50_FILE)
            col = 'Symbol' if 'Symbol' in df.columns else df.columns[0]
            return df[col].dropna().unique().tolist()
        except Exception as e:
            logger.error(f"Error loading {NIFTY50_FILE}: {e}")

    if segment == 'nifty500' and os.path.exists(NIFTY500_FILE):
        try:
            df = pd.read_csv(NIFTY500_FILE)
            col = 'Symbol' if 'Symbol' in df.columns else df.columns[2]
            return df[col].dropna().unique().tolist()
        except Exception as e:
            logger.error(f"Error loading {NIFTY500_FILE}: {e}")

    if segment in ['all', 'universe', 'parquet']:
        # 1. First check Zerodha parquet historical data directory (~2,294 stocks)
        try:
            import app
            parquet_syms = app.get_available_parquet_symbols()
            if parquet_syms:
                return parquet_syms
        except Exception:
            pass

        # 2. Direct directory read fallback
        zerodha_dir = r"C:\Zerodha Historical Data\data\minute"
        if os.path.exists(zerodha_dir):
            try:
                files = os.listdir(zerodha_dir)
                syms = [f[:-8] for f in files if f.endswith('.parquet')]
                if syms:
                    return sorted(syms)
            except Exception as e:
                logger.error(f"Error reading {zerodha_dir}: {e}")

        # 3. Fallback to consolidated database if present
        cons_file = os.path.join(DATA_DIR, 'consolidated_data.csv')
        if os.path.exists(cons_file):
            try:
                df = pd.read_csv(cons_file, usecols=['Symbol'])
                return df['Symbol'].dropna().unique().tolist()
            except Exception as e:
                logger.error(f"Error loading {cons_file}: {e}")

        # 4. Fallback to Nifty 500
        if os.path.exists(NIFTY500_FILE):
            try:
                df = pd.read_csv(NIFTY500_FILE)
                col = 'Symbol' if 'Symbol' in df.columns else df.columns[2]
                return df[col].dropna().unique().tolist()
            except Exception:
                pass

    return ['TCS', 'INFY', 'RELIANCE', 'HDFCBANK', 'ICICIBANK']


def main():
    parser = argparse.ArgumentParser(description="Download NSE Stock Fundamentals (P&L, Balance Sheet, Ratios)")
    parser.add_argument('--segment', type=str, default='nifty50', choices=['nifty50', 'nifty500', 'all', 'parquet', 'universe'],
                        help="Stock universe segment to download: 'nifty50' (50 stocks), 'nifty500' (500 stocks), or 'all'/'parquet' (~2,294 stocks) (default: nifty50)")
    parser.add_argument('--symbols', type=str, default=None,
                        help="Comma-separated symbols to download (e.g. 'TCS,INFY,RELIANCE')")
    parser.add_argument('--force', action='store_true',
                        help="Force re-download even if already cached within 7 days")
    parser.add_argument('--delay', type=float, default=0.35,
                        help="Delay in seconds between stock requests (default: 0.35s)")
    args = parser.parse_args()

    print("=" * 65)
    print("NSE FUNDAMENTALS DOWNLOADER (Quarterly/Yearly P&L, Balance Sheet, Ratios)")
    print("=" * 65)

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
        print(f"Targeting {len(symbols)} specified symbols: {symbols}")
    else:
        symbols = get_symbols_for_segment(args.segment)
        print(f"Targeting segment '{args.segment}' ({len(symbols)} symbols)")

    start_t = time.time()
    download_fundamentals_batch(symbols, force=args.force, delay=args.delay)
    elapsed = round(time.time() - start_t, 1)

    print("=" * 65)
    print(f"Completed in {elapsed}s.")
    print(f"Ratios summary: {RATIOS_SUMMARY_JSON}")
    print(f"Detailed statements directory: {STATEMENTS_DIR}")
    print("=" * 65)


if __name__ == '__main__':
    main()

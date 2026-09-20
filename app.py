import os
import io
import re
import time
import logging
import json
import webbrowser
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import duckdb
from flask import Flask, request, jsonify, render_template, send_file

try:
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as RLImage
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Directory Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BHAV_DIR = os.path.join(DATA_DIR, 'bhavcopies')
CONSOLIDATED_FILE = os.path.join(DATA_DIR, 'consolidated_data.csv')
SPLITS_CACHE_FILE = os.path.join(DATA_DIR, 'splits_cache.json')
MARKET_CAP_CACHE_FILE = os.path.join(DATA_DIR, 'market_cap_cache.json')
FUNDAMENTALS_DIR = os.path.join(DATA_DIR, 'fundamentals')
STATEMENTS_DIR = os.path.join(FUNDAMENTALS_DIR, 'statements')
RATIOS_SUMMARY_FILE = os.path.join(FUNDAMENTALS_DIR, 'ratios_summary.json')
STRATEGIES_FILE = os.path.join(DATA_DIR, 'strategies.json')
BACKTEST_STRATEGIES_FILE = os.path.join(DATA_DIR, 'backtest_strategies.json')
NIFTY50_FILE = os.path.join(DATA_DIR, 'nifty50.csv')
NIFTY500_FILE = os.path.join(DATA_DIR, 'nifty500.csv')
FNO_FILE = os.path.join(DATA_DIR, 'fno.csv')

# Zerodha Historical Minute Parquet Directory
ZERODHA_MINUTE_DIR = r"C:\Zerodha Historical Data\data\minute"
ADJUSTED_DAILY_DIR = os.path.join(DATA_DIR, 'adjusted_daily')

# Ensure local directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BHAV_DIR, exist_ok=True)
os.makedirs(FUNDAMENTALS_DIR, exist_ok=True)
os.makedirs(STATEMENTS_DIR, exist_ok=True)
os.makedirs(ADJUSTED_DAILY_DIR, exist_ok=True)

# Column mapping from raw NSE to cleaned dashboard columns
COLUMN_MAP = {
    'SYMBOL': 'Symbol',
    'SERIES': 'Series',
    'DATE1': 'Date',
    'PREV_CLOSE': 'Prev_Close',
    'OPEN_PRICE': 'Open',
    'HIGH_PRICE': 'High',
    'LOW_PRICE': 'Low',
    'LAST_PRICE': 'Last',
    'CLOSE_PRICE': 'Close',
    'AVG_PRICE': 'Avg_Price',
    'TTL_TRD_QNTY': 'Volume',
    'TURNOVER_LACS': 'Turnover_Lacs',
    'NO_OF_TRADES': 'No_Of_Trades',
    'DELIV_QTY': 'Deliv_Qty',
    'DELIV_PER': 'Deliv_Per'
}

# --- DuckDB Connection Pool / Helpers ---

def get_duckdb_connection():
    return duckdb.connect()

def get_ticker_parquet_path(symbol):
    symbol = symbol.upper().strip()
    p = os.path.join(ZERODHA_MINUTE_DIR, f"{symbol}.parquet")
    if os.path.exists(p):
        return p
    return None

def get_available_parquet_symbols():
    if not os.path.exists(ZERODHA_MINUTE_DIR):
        return []
    try:
        files = os.listdir(ZERODHA_MINUTE_DIR)
        symbols = [f[:-8] for f in files if f.endswith('.parquet')]
        return sorted(symbols)
    except Exception as e:
        logger.error(f"Error listing parquet symbols: {e}")
        return []

# --- Splits & Corporate Actions Management ---

def load_splits_cache():
    if os.path.exists(SPLITS_CACHE_FILE) and os.path.getsize(SPLITS_CACHE_FILE) > 0:
        try:
            with open(SPLITS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading splits cache: {e}")
    return {}

def save_splits_cache(cache):
    try:
        with open(SPLITS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving splits cache: {e}")

def get_splits_for_stock(symbol, fetch_online=False):
    splits_cache = load_splits_cache()
    symbol = symbol.upper()
    if symbol in splits_cache:
        return splits_cache[symbol]

    if not fetch_online:
        return {}

    splits_dict = {}
    try:
        logger.info(f"Fetching corporate actions splits from yfinance for {symbol}...")
        ticker = yf.Ticker(f"{symbol}.NS")
        splits = ticker.splits
        if not splits.empty:
            for dt, ratio in splits.items():
                date_str = dt.strftime('%Y-%m-%d')
                splits_dict[date_str] = float(ratio)
        splits_cache[symbol] = splits_dict
        save_splits_cache(splits_cache)
    except Exception as e:
        logger.error(f"Error fetching splits for {symbol}: {e}")
        return {}
    return splits_dict

# --- Market Capitalization Cache & Helper ---

_MARKET_CAP_CACHE = None

def load_market_cap_cache():
    global _MARKET_CAP_CACHE
    if _MARKET_CAP_CACHE is not None:
        return _MARKET_CAP_CACHE
    if os.path.exists(MARKET_CAP_CACHE_FILE) and os.path.getsize(MARKET_CAP_CACHE_FILE) > 0:
        try:
            with open(MARKET_CAP_CACHE_FILE, 'r', encoding='utf-8') as f:
                _MARKET_CAP_CACHE = json.load(f)
                return _MARKET_CAP_CACHE
        except Exception as e:
            logger.error(f"Error loading market cap cache: {e}")
    _MARKET_CAP_CACHE = {}
    return _MARKET_CAP_CACHE

def save_market_cap_cache(cache):
    try:
        with open(MARKET_CAP_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving market cap cache: {e}")

def get_market_cap_cr(symbol, fetch_online=True):
    """
    Returns company Market Capitalization in Crores (₹ Cr).
    Uses data/market_cap_cache.json, falling back to yfinance fast_info.
    """
    cache = load_market_cap_cache()
    sym = str(symbol).upper().strip()
    if sym in cache and cache[sym] is not None and float(cache[sym]) > 0:
        return float(cache[sym])

    if not fetch_online:
        return 0.0

    try:
        ticker = yf.Ticker(f"{sym}.NS")
        mc = ticker.fast_info.get('marketCap')
        if not mc:
            mc = ticker.info.get('marketCap')
        if mc:
            mc_cr = round(float(mc) / 1e7, 2)
            cache[sym] = mc_cr
            save_market_cap_cache(cache)
            return mc_cr
        else:
            cache[sym] = 0.0
            save_market_cap_cache(cache)
            return 0.0
    except Exception as e:
        logger.debug(f"Could not fetch market cap for {sym}: {e}")
        return 0.0

# --- Fundamentals Cache & Helpers ---

_FUNDAMENTALS_CACHE = None
FUNDAMENTALS_SYNC_STATUS = {
    "is_running": False,
    "current": 0,
    "total": 0,
    "current_symbol": "",
    "status": "idle",
    "last_sync": None
}

def load_fundamentals_cache(force_reload=False):
    """
    Loads all stock ratios from data/fundamentals/ratios_summary.json into memory.
    """
    global _FUNDAMENTALS_CACHE
    if _FUNDAMENTALS_CACHE is not None and not force_reload:
        return _FUNDAMENTALS_CACHE
    if os.path.exists(RATIOS_SUMMARY_FILE) and os.path.getsize(RATIOS_SUMMARY_FILE) > 0:
        try:
            with open(RATIOS_SUMMARY_FILE, 'r', encoding='utf-8') as f:
                _FUNDAMENTALS_CACHE = json.load(f)
                return _FUNDAMENTALS_CACHE
        except Exception as e:
            logger.error(f"Error loading fundamentals cache: {e}")
    _FUNDAMENTALS_CACHE = {}
    return _FUNDAMENTALS_CACHE

def save_fundamentals_cache(cache):
    try:
        with open(RATIOS_SUMMARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving fundamentals cache: {e}")

def get_stock_fundamentals(symbol, fetch_online=False):
    """
    Returns fundamental financial ratios dictionary for symbol:
    pe, forwardPE, pb, roe, roa, debtToEquity, currentRatio, quickRatio,
    operatingMargin, profitMargin, dividendYield, marketCapCr, etc.
    """
    cache = load_fundamentals_cache()
    sym = str(symbol).upper().replace('.NS', '').strip()
    if sym in cache and cache[sym]:
        return cache[sym]

    if not fetch_online:
        return {}

    try:
        from download_fundamentals import download_fundamentals_for_symbol
        res = download_fundamentals_for_symbol(sym, force=True)
        if res and res.get('ratios'):
            cache[sym] = res['ratios']
            return res['ratios']
    except Exception as e:
        logger.debug(f"Could not fetch online fundamentals for {sym}: {e}")
    return {}

def get_stock_statement(symbol, fetch_online=False):
    """
    Loads full financial statements (quarterly_pnl, yearly_pnl, balance_sheet, cashflow)
    from data/fundamentals/statements/{symbol}.json.
    """
    sym = str(symbol).upper().replace('.NS', '').strip()
    stmt_file = os.path.join(STATEMENTS_DIR, f"{sym}.json")
    if os.path.exists(stmt_file):
        try:
            with open(stmt_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading statement for {sym}: {e}")

    if fetch_online:
        try:
            from download_fundamentals import download_fundamentals_for_symbol
            return download_fundamentals_for_symbol(sym, force=True)
        except Exception as e:
            logger.error(f"Error downloading statement for {sym}: {e}")
    return {}

def adjust_parquet_splits(df, symbol):
    """
    Intelligently adjusts historical prices for corporate actions/splits.
    Inspects prices right before and after each split date (from newest to oldest)
    to verify whether the data is already pre-adjusted. Only applies adjustment if unadjusted,
    preventing erroneous double-adjustments.
    """
    splits = get_splits_for_stock(symbol, fetch_online=False)
    if not splits or df.empty:
        return df

    df_adj = df.copy()
    if 'Date' in df_adj.columns:
        df_adj['Date_str'] = df_adj['Date'].astype(str).str.slice(0, 10)
    elif 'date' in df_adj.columns:
        df_adj['Date_str'] = df_adj['date'].astype(str).str.slice(0, 10)
    else:
        return df_adj

    sorted_splits = sorted(splits.items(), key=lambda x: x[0], reverse=True)

    for split_date, ratio in sorted_splits:
        if ratio <= 0 or ratio == 1.0:
            continue

        mask_before = df_adj['Date_str'] < split_date
        mask_after = df_adj['Date_str'] >= split_date
        if not mask_before.any() or not mask_after.any():
            continue

        c_col = 'Close' if 'Close' in df_adj.columns else 'close'
        c_before = df_adj.loc[mask_before, c_col].iloc[-1]
        c_after = df_adj.loc[mask_after, c_col].iloc[0]
        observed_ratio = (c_before / c_after) if c_after > 0 else 1.0

        # If observed_ratio is close to split ratio, the data prior to split is unadjusted
        if abs(observed_ratio - ratio) < (0.25 * ratio):
            logger.info(f"Applying split adjustment of {ratio} on {symbol} before {split_date}")
            for col in ['open', 'high', 'low', 'close', 'prev_close', 'Open', 'High', 'Low', 'Close', 'Prev_Close']:
                if col in df_adj.columns:
                    df_adj.loc[mask_before, col] = (df_adj.loc[mask_before, col] / ratio).round(2)
            for col in ['volume', 'Volume']:
                if col in df_adj.columns:
                    df_adj.loc[mask_before, col] = (df_adj.loc[mask_before, col] * ratio).round(0)

    df_adj = df_adj.drop(columns=['Date_str'], errors='ignore')
    if 'Close' in df_adj.columns:
        df_adj['Prev_Close'] = df_adj['Close'].shift(1).fillna(df_adj.get('Open', df_adj['Close'])).round(2)

    return df_adj

# --- Querying Parquet Data via DuckDB Across Timeframes ---

def get_ticker_data_duckdb(symbol, timeframe='1d', start_date=None, end_date=None, auto_adjust=True):
    """
    Queries 1-minute Parquet files using DuckDB and dynamically resamples into:
    '1m' (1 Minute), '5m' (5 Minutes), '15m' (15 Minutes), '1h' (1 Hour), '1d' (Daily / EOD).
    Applies corporate actions / splits auto-adjustment.
    """
    symbol = symbol.upper().strip()
    timeframe = timeframe.lower()

    # -------------------------------------------------------------------------
    # Fast Path: Pre-Adjusted Daily Parquet Cache (10x Faster EOD Execution)
    # Reads directly from data/adjusted_daily/{SYMBOL}.parquet, bypassing heavy
    # 1-minute aggregation and on-the-fly split recalculation.
    # -------------------------------------------------------------------------
    if timeframe in ['1d', 'daily', 'day']:
        adj_daily_path = os.path.join(ADJUSTED_DAILY_DIR, f"{symbol}.parquet")
        if os.path.exists(adj_daily_path):
            try:
                con = get_duckdb_connection()
                time_filter = ""
                params = [adj_daily_path.replace('\\', '/')]
                if start_date:
                    start_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, (datetime, pd.Timestamp)) else str(start_date)[:10]
                    time_filter += " AND date >= ?"
                    params.append(start_str)
                if end_date:
                    end_str = end_date.strftime('%Y-%m-%d') if isinstance(end_date, (datetime, pd.Timestamp)) else str(end_date)[:10]
                    time_filter += " AND date <= ?"
                    params.append(end_str)

                sql = f"""
                    SELECT date, open, high, low, close, volume, prev_close
                    FROM read_parquet(?)
                    WHERE 1=1 {time_filter}
                    ORDER BY date ASC
                """
                df = con.execute(sql, params).fetchdf()
                if not df.empty:
                    df['Date'] = df['date'].astype(str)
                    df['Open'] = df['open'].round(2)
                    df['High'] = df['high'].round(2)
                    df['Low'] = df['low'].round(2)
                    df['Close'] = df['close'].round(2)
                    df['Volume'] = df['volume'].round(0).astype('int64', errors='ignore')
                    df['Prev_Close'] = df['prev_close'].round(2)
                    df['Symbol'] = symbol

                    mcap_val = get_market_cap_cr(symbol, fetch_online=False)
                    fund = get_stock_fundamentals(symbol, fetch_online=False)
                    if (not mcap_val or mcap_val == 0.0) and fund and fund.get('marketCapCr'):
                        mcap_val = fund['marketCapCr']
                    df['Market_Cap_Cr'] = mcap_val

                    if fund:
                        df['PE'] = fund.get('pe')
                        df['Forward_PE'] = fund.get('forwardPE')
                        df['PB'] = fund.get('pb')
                        df['ROE'] = fund.get('roe')
                        df['ROA'] = fund.get('roa')
                        df['Debt_To_Equity'] = fund.get('debtToEquity')
                        df['Operating_Margin'] = fund.get('operatingMargin')
                        df['Profit_Margin'] = fund.get('profitMargin')
                        df['Dividend_Yield'] = fund.get('dividendYield')

                    df.index = pd.to_datetime(df['date']).astype('datetime64[ns]')
                    return df
            except Exception as e:
                logger.warning(f"Error querying adjusted daily cache for {symbol}: {e}. Falling back to 1-minute aggregation.")

    parquet_path = get_ticker_parquet_path(symbol)
    if not parquet_path:
        return pd.DataFrame()

    con = get_duckdb_connection()

    # Timeframe SQL generation
    time_filter = ""
    params = [parquet_path.replace('\\', '/')]

    if start_date:
        start_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, (datetime, pd.Timestamp)) else str(start_date)
        time_filter += " AND date >= ?"
        params.append(start_str)

    if end_date:
        end_str = end_date.strftime('%Y-%m-%d') if isinstance(end_date, (datetime, pd.Timestamp)) else str(end_date)
        time_filter += " AND date <= ?"
        params.append(end_str + " 23:59:59")

    try:
        if timeframe in ['1d', 'daily', 'day']:
            sql = f"""
                SELECT 
                    CAST(date AS DATE) AS date,
                    FIRST(open) AS open,
                    MAX(high) AS high,
                    MIN(low) AS low,
                    LAST(close) AS close,
                    SUM(volume) AS volume
                FROM read_parquet(?)
                WHERE 1=1 {time_filter}
                GROUP BY 1
                ORDER BY 1 ASC
            """
        elif timeframe in ['5m', '5min', '5mins']:
            sql = f"""
                SELECT 
                    time_bucket(INTERVAL '5 Minutes', date) AS date,
                    FIRST(open) AS open,
                    MAX(high) AS high,
                    MIN(low) AS low,
                    LAST(close) AS close,
                    SUM(volume) AS volume
                FROM read_parquet(?)
                WHERE 1=1 {time_filter}
                GROUP BY 1
                ORDER BY 1 ASC
            """
        elif timeframe in ['15m', '15min', '15mins']:
            sql = f"""
                SELECT 
                    time_bucket(INTERVAL '15 Minutes', date) AS date,
                    FIRST(open) AS open,
                    MAX(high) AS high,
                    MIN(low) AS low,
                    LAST(close) AS close,
                    SUM(volume) AS volume
                FROM read_parquet(?)
                WHERE 1=1 {time_filter}
                GROUP BY 1
                ORDER BY 1 ASC
            """
        elif timeframe in ['1h', '60m', '1hour', 'hour']:
            sql = f"""
                SELECT 
                    time_bucket(INTERVAL '1 Hour', date, INTERVAL '15 Minutes') AS date,
                    FIRST(open) AS open,
                    MAX(high) AS high,
                    MIN(low) AS low,
                    LAST(close) AS close,
                    SUM(volume) AS volume
                FROM read_parquet(?)
                WHERE 1=1 {time_filter}
                GROUP BY 1
                ORDER BY 1 ASC
            """
        else: # Default: 1 minute
            sql = f"""
                SELECT 
                    date,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM read_parquet(?)
                WHERE 1=1 {time_filter}
                ORDER BY date ASC
            """

        df = con.execute(sql, params).fetchdf()
    except Exception as e:
        logger.error(f"Error executing DuckDB query for {symbol} ({timeframe}): {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # Format date string column
    if timeframe in ['1d', 'daily', 'day']:
        df['Date'] = df['date'].astype(str)
    else:
        df['Date'] = df['date'].dt.strftime('%Y-%m-%d %H:%M')

    # Standardize columns for both uppercase and lowercase access
    df['Open'] = df['open'].round(2)
    df['High'] = df['high'].round(2)
    df['Low'] = df['low'].round(2)
    df['Close'] = df['close'].round(2)
    df['Volume'] = df['volume'].round(0).astype('int64', errors='ignore')
    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Open']).round(2)
    mcap_val = get_market_cap_cr(symbol, fetch_online=False)
    fund = get_stock_fundamentals(symbol, fetch_online=False)
    if (not mcap_val or mcap_val == 0.0) and fund and fund.get('marketCapCr'):
        mcap_val = fund['marketCapCr']

    df['Symbol'] = symbol
    df['Market_Cap_Cr'] = mcap_val

    # Attach key fundamentals if available in local cache
    if fund:
        df['PE'] = fund.get('pe')
        df['Forward_PE'] = fund.get('forwardPE')
        df['PB'] = fund.get('pb')
        df['ROE'] = fund.get('roe')
        df['ROA'] = fund.get('roa')
        df['Debt_To_Equity'] = fund.get('debtToEquity')
        df['Operating_Margin'] = fund.get('operatingMargin')
        df['Profit_Margin'] = fund.get('profitMargin')
        df['Dividend_Yield'] = fund.get('dividendYield')

    if auto_adjust:
        df = adjust_parquet_splits(df, symbol)

    # Assign DatetimeIndex for resample support (standardize to nanoseconds)
    if not df.empty and 'date' in df.columns:
        df.index = pd.to_datetime(df['date']).astype('datetime64[ns]')

    return df

# --- Consolidated Database & Cache ---

_DB_CACHE = None

def load_database(force_reload=False):
    global _DB_CACHE
    if _DB_CACHE is not None and not force_reload:
        return _DB_CACHE

    if os.path.exists(CONSOLIDATED_FILE) and os.path.getsize(CONSOLIDATED_FILE) > 0:
        try:
            logger.info("Loading consolidated database into memory...")
            start_time = time.time()
            df = pd.read_csv(CONSOLIDATED_FILE)
            df['Date'] = df['Date'].astype(str)
            df['Symbol'] = df['Symbol'].astype(str)
            df = df.sort_values(by=['Date', 'Symbol'], ascending=[False, True])
            _DB_CACHE = df
            logger.info(f"Loaded {len(df)} records in {time.time() - start_time:.2f} seconds.")
            return _DB_CACHE
        except Exception as e:
            logger.error(f"Error loading database into memory: {e}")
    _DB_CACHE = pd.DataFrame()
    return _DB_CACHE

# Backward compatibility functions
def format_date_for_url(date_obj):
    return date_obj.strftime("%d%m%Y")

def format_date_to_db(date_str):
    try:
        date_str = date_str.strip()
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        dt = datetime.strptime(date_str, "%d-%b-%Y")
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        logger.error(f"Error parsing date {date_str}: {e}")
        return date_str

def clean_bhavcopy(df):
    df.columns = df.columns.str.strip()
    mapped_cols = {}
    for raw_col, clean_col in COLUMN_MAP.items():
        if raw_col in df.columns:
            mapped_cols[raw_col] = clean_col

    df = df.rename(columns=mapped_cols)
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()

    if 'Series' in df.columns:
        df = df[df['Series'].isin(['EQ', 'BE', 'SM'])]

    if 'Date' in df.columns:
        df['Date'] = df['Date'].apply(format_date_to_db)

    numeric_cols = ['Prev_Close', 'Open', 'High', 'Low', 'Last', 'Close', 'Avg_Price', 
                    'Volume', 'Turnover_Lacs', 'No_Of_Trades', 'Deliv_Qty', 'Deliv_Per']

    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    final_cols = [c for c in COLUMN_MAP.values() if c in df.columns]
    return df[final_cols]

def download_bhavcopy_from_nse(date_obj):
    date_str_url = format_date_for_url(date_obj)
    url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_str_url}.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/"
    }

    logger.info(f"Attempting to download Bhavcopy for {date_obj.strftime('%Y-%m-%d')} from: {url}")
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
    except Exception as e:
        logger.warning(f"Could not establish session on NSE homepage: {e}")

    try:
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            if "SYMBOL" in response.text or "SYMBOL" in response.text.upper():
                return response.text
            return None
        return None
    except Exception as e:
        logger.error(f"Request exception while downloading Bhavcopy: {e}")
        return None

def save_daily_bhav(date_obj, raw_csv_text):
    os.makedirs(BHAV_DIR, exist_ok=True)
    filename = f"sec_bhavdata_full_{format_date_for_url(date_obj)}.csv"
    filepath = os.path.join(BHAV_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(raw_csv_text)
    return filepath

def update_consolidated_database(cleaned_df, current_db_df):
    global _DB_CACHE
    if cleaned_df.empty:
        return current_db_df

    new_dates = cleaned_df['Date'].unique()
    if not current_db_df.empty:
        updated_db = current_db_df[~current_db_df['Date'].isin(new_dates)]
    else:
        updated_db = pd.DataFrame(columns=cleaned_df.columns)

    updated_db = pd.concat([updated_db, cleaned_df], ignore_index=True)
    updated_db = updated_db.sort_values(by=['Date', 'Symbol'], ascending=[False, True])

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        updated_db.to_csv(CONSOLIDATED_FILE, index=False)
        _DB_CACHE = updated_db
        logger.info(f"Database updated and saved. Total records: {len(updated_db)}")
    except Exception as e:
        logger.error(f"Failed to write database file: {e}")

    return updated_db

# --- Stock Constituent Lists ---

def fetch_nifty50_symbols():
    if os.path.exists(NIFTY50_FILE) and os.path.getsize(NIFTY50_FILE) > 0:
        try:
            df = pd.read_csv(NIFTY50_FILE)
            return df['Symbol'].dropna().str.strip().tolist()
        except Exception as e:
            logger.error(f"Error reading local Nifty 50 file: {e}")

    try:
        url = "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = df.columns.str.strip()
            df.to_csv(NIFTY50_FILE, index=False)
            return df['Symbol'].dropna().str.strip().tolist()
    except Exception as e:
        logger.error(f"Failed to fetch Nifty 50 online: {e}")

    return ['ADANIENT', 'ADANIPORTS', 'APOLLOHOSP', 'ASIANPAINT', 'AXISBANK', 'BAJAJ-AUTO', 'BAJFINANCE', 'BAJAJFINSV', 'BHARTIARTL', 'BPCL', 'BRITANNIA', 'CIPLA', 'COALINDIA', 'DIVISLAB', 'DRREDDY', 'EICHERMOT', 'GRASIM', 'HCLTECH', 'HDFCBANK', 'HDFCLIFE', 'HEROMOTOCO', 'HINDALCO', 'HINDUNILVR', 'ICICIBANK', 'INDUSINDBK', 'INFY', 'ITC', 'JSWSTEEL', 'KOTAKBANK', 'LT', 'LTIM', 'M&M', 'MARUTI', 'NESTLEIND', 'NTPC', 'ONGC', 'POWERGRID', 'RELIANCE', 'SBILIFE', 'SBIN', 'SUNPHARMA', 'TATACONSUM', 'TATAMOTORS', 'TATASTEEL', 'TCS', 'TECHM', 'TITAN', 'ULTRACEMCO', 'WIPRO']

def fetch_nifty500_symbols():
    if os.path.exists(NIFTY500_FILE) and os.path.getsize(NIFTY500_FILE) > 0:
        try:
            df = pd.read_csv(NIFTY500_FILE)
            return df['Symbol'].dropna().str.strip().tolist()
        except Exception as e:
            logger.error(f"Error reading local Nifty 500 file: {e}")

    try:
        url = "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = df.columns.str.strip()
            df.to_csv(NIFTY500_FILE, index=False)
            return df['Symbol'].dropna().str.strip().tolist()
    except Exception as e:
        logger.error(f"Failed to fetch Nifty 500 online: {e}")

    return []

def fetch_fno_symbols():
    if os.path.exists(FNO_FILE) and os.path.getsize(FNO_FILE) > 0:
        try:
            df = pd.read_csv(FNO_FILE)
            return df['Symbol'].dropna().str.strip().tolist()
        except Exception as e:
            logger.error(f"Error reading local FnO file: {e}")

    try:
        url = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = df.columns.str.strip()
            symbol_col = None
            for col in df.columns:
                if 'UNDERLYING' in col.upper() or 'SYMBOL' in col.upper():
                    symbol_col = col
                    break
            if symbol_col:
                symbols = df[symbol_col].dropna().str.strip().unique().tolist()
                symbols = [s for s in symbols if s not in ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTYNXT50', 'Symbol']]
                pd.DataFrame({'Symbol': sorted(symbols)}).to_csv(FNO_FILE, index=False)
                return sorted(symbols)
    except Exception as e:
        logger.error(f"Failed to fetch FnO list online: {e}")

    return []

def compute_r2_cross_date_fallback(df_symbol, match_dt):
    """
    Finds the date when the initial candle crossed above monthly R2
    prior to or on match_dt.
    """
    try:
        df = df_symbol.copy()
        if df.empty:
            return "-"
        
        if not isinstance(df.index, pd.DatetimeIndex):
            dt_col = 'date' if 'date' in df.columns else ('Date' if 'Date' in df.columns else None)
            if dt_col:
                df.index = pd.to_datetime(df[dt_col])
            else:
                return "-"
            
        daily = df.resample('1D').agg({
            'open': 'first' if 'open' in df.columns else 'Open',
            'high': 'max' if 'high' in df.columns else 'High',
            'low': 'min' if 'low' in df.columns else 'Low',
            'close': 'last' if 'close' in df.columns else 'Close',
            'volume': 'sum' if 'volume' in df.columns else 'Volume'
        }).dropna(subset=['close'])
        
        if daily.empty:
            return "-"

        daily['Month'] = daily.index.to_period('M')
        monthly = daily.groupby('Month').agg({
            'high': 'max',
            'low': 'min',
            'close': 'last'
        }).shift(1)
        
        monthly['Pivot'] = (monthly['high'] + monthly['low'] + monthly['close']) / 3
        monthly['R2'] = monthly['Pivot'] + (monthly['high'] - monthly['low'])
        
        daily['R2'] = daily['Month'].map(monthly['R2'])
        
        raw_cross = (daily['high'] >= daily['R2'])
        had_recent = (
            raw_cross.shift(1)
            .rolling('62D', min_periods=1)
            .max()
            .fillna(0)
            .astype(bool)
        )
        vol_ok = daily['volume'] >= 500_000 if 'volume' in daily.columns else True
        stage1_events = daily[raw_cross & (~had_recent) & vol_ok]
        
        match_dt_parsed = pd.to_datetime(match_dt)
        prior_events = stage1_events[stage1_events.index <= match_dt_parsed]
        if not prior_events.empty:
            return prior_events.index[-1].strftime('%Y-%m-%d')
            
        any_cross = daily[(daily['high'] >= daily['R2']) & (daily.index <= match_dt_parsed)]
        if not any_cross.empty:
            return any_cross.index[-1].strftime('%Y-%m-%d')
            
    except Exception as e:
        logger.error(f"Error computing fallback R2 date: {e}")
    return "-"

def run_screener_logic(code_str, segment, timeframe='1d', watchlist_symbols=None, start_date=None, end_date=None, min_market_cap_cr=2000.0):
    """
    Executes user's custom python screen(df) logic across multiple timeframes (1m, 5m, 15m, 1h, 1d)
    using DuckDB for high performance.
    """
    symbols = []
    if segment == 'nifty50':
        symbols = fetch_nifty50_symbols()
    elif segment == 'nifty500':
        symbols = fetch_nifty500_symbols()
    elif segment == 'fno':
        symbols = fetch_fno_symbols()
    elif segment == 'watchlist' and watchlist_symbols:
        symbols = watchlist_symbols
    else:
        # All available symbols in Zerodha Parquet directory
        symbols = get_available_parquet_symbols()
        if not symbols:
            db_df = load_database()
            if not db_df.empty:
                symbols = db_df['Symbol'].dropna().unique().tolist()

    exec_env = {
        '__builtins__': __builtins__,
        'pd': pd,
        'np': np,
        'yf': yf,
        'datetime': datetime,
        'timedelta': timedelta,
        'get_market_cap_cr': get_market_cap_cr,
        'get_stock_fundamentals': get_stock_fundamentals,
        'get_fundamentals': get_stock_fundamentals,
        'get_stock_statement': get_stock_statement,
        'load_fundamentals_cache': load_fundamentals_cache,
    }
    try:
        exec(code_str, exec_env)
        screen_func = None
        for name in ['screen', 'backtest', 'strategy']:
            if name in exec_env and callable(exec_env[name]):
                screen_func = exec_env[name]
                break
        if not screen_func:
            return {"status": "error", "message": "The code must define a callable function named 'screen(df)' or 'backtest(df)'"}
    except Exception as e:
        return {"status": "error", "message": f"Compile error: {str(e)}"}

    start_time = time.time()
    logger.info(f"Screening {len(symbols)} stocks on timeframe '{timeframe}' using custom code...")

    historical_results = {}
    total_matches = 0
    error_count = 0
    last_error = ""

    for symbol in symbols:
        mcap_cr = get_market_cap_cr(symbol, fetch_online=True)
        if min_market_cap_cr > 0 and mcap_cr > 0 and mcap_cr < min_market_cap_cr:
            continue

        # Fetch full history (or up to end_date) so multi-timeframe pivots, rolling volume & EMAs have complete warm-up data
        df_symbol = get_ticker_data_duckdb(symbol, timeframe=timeframe, start_date=None, end_date=end_date)
        if df_symbol.empty:
            continue

        try:
            res = screen_func(df_symbol)

            signal_series = None
            custom_series = {}

            if isinstance(res, pd.Series):
                signal_series = res
            elif isinstance(res, dict):
                sig = None
                for sig_k in ['long_entry', 'entries', 'signal', 'buy_signal']:
                    if sig_k in res and res[sig_k] is not None:
                        sig = res[sig_k]
                        break
                if isinstance(sig, pd.Series):
                    signal_series = sig
                elif isinstance(sig, (np.ndarray, list)):
                    signal_series = pd.Series(sig, index=df_symbol.index[:len(sig)])
                elif isinstance(sig, (bool, np.bool_)):
                    signal_series = pd.Series([False] * len(df_symbol), index=df_symbol.index)
                    if len(df_symbol) > 0:
                        signal_series.iloc[-1] = bool(sig)

                for k, v in res.items():
                    if k in ['signal', 'entries', 'long_entry', 'buy_signal', 'df', 'data', 'dataframe'] or isinstance(v, pd.DataFrame):
                        continue
                    if isinstance(v, pd.Series):
                        custom_series[k] = v
                    elif isinstance(v, (np.ndarray, list)):
                        custom_series[k] = pd.Series(v, index=df_symbol.index[:len(v)])
                    else:
                        custom_series[k] = pd.Series([v] * len(df_symbol), index=df_symbol.index)
            elif isinstance(res, (np.ndarray, list)):
                signal_series = pd.Series(res, index=df_symbol.index[:len(res)])
            elif isinstance(res, (bool, np.bool_)):
                signal_series = pd.Series([False] * len(df_symbol), index=df_symbol.index)
                if len(df_symbol) > 0:
                    signal_series.iloc[-1] = bool(res)
            else:
                continue

            if signal_series is None or len(signal_series) == 0:
                continue

            true_mask = (signal_series == True)
            if not true_mask.any():
                continue

            # Case A: 1-to-1 matching timeline (signal length matches df_symbol)
            if len(signal_series) == len(df_symbol):
                signal_series.index = df_symbol.index
                match_indices = df_symbol.index[signal_series == True]
                for idx in match_indices:
                    row = df_symbol.loc[idx]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[-1]
                    date_str = str(row['Date'])

                    # Filter matches within user's requested date window
                    if start_date and date_str[:10] < str(start_date)[:10]:
                        continue
                    if end_date and date_str[:10] > str(end_date)[:10]:
                        continue

                    custom_data = {}
                    for k, s_val in custom_series.items():
                        try:
                            val = s_val.loc[idx] if idx in s_val.index else s_val.iloc[-1]
                            if isinstance(val, pd.Series):
                                val = val.iloc[-1]
                            if hasattr(val, 'item'):
                                val = val.item()
                            custom_data[k] = round(val, 2) if isinstance(val, (float, np.floating)) else val
                        except Exception:
                            custom_data[k] = '-'

                    idx_pos = df_symbol.index.get_loc(idx)
                    if isinstance(idx_pos, np.ndarray):
                        idx_pos = idx_pos[-1]
                    pct_change = 0.0
                    if idx_pos > 0:
                        prev_row = df_symbol.iloc[idx_pos - 1]
                        if prev_row['Close'] > 0:
                            pct_change = ((row['Close'] - prev_row['Close']) / prev_row['Close'] * 100)

                    if not custom_data.get("R2_Cross_Date") or custom_data.get("R2_Cross_Date") == '-':
                        custom_data["R2_Cross_Date"] = compute_r2_cross_date_fallback(df_symbol, date_str)

                    res_item = {
                        "Date": date_str,
                        "Symbol": symbol,
                        "Close": float(row['Close']),
                        "Pct_Change": round(float(pct_change), 2),
                        "Volume": int(row['Volume']),
                        "Market_Cap_Cr": round(float(mcap_cr), 2) if mcap_cr else 0.0,
                        "custom_data": custom_data
                    }

                    if date_str not in historical_results:
                        historical_results[date_str] = []
                    historical_results[date_str].append(res_item)
                    total_matches += 1

            # Case B: Multi-timeframe resampled timeline (e.g., 1H signal derived from 1m data)
            else:
                matching_times = signal_series.index[true_mask]
                for ts in matching_times:
                    ts_dt = pd.to_datetime(ts)
                    date_str = ts_dt.strftime('%Y-%m-%d %H:%M') if timeframe != '1d' else ts_dt.strftime('%Y-%m-%d')

                    if start_date and date_str[:10] < str(start_date)[:10]:
                        continue
                    if end_date and date_str[:10] > str(end_date)[:10]:
                        continue

                    matched_slice = df_symbol[df_symbol.index <= ts_dt]
                    if matched_slice.empty:
                        matched_slice = df_symbol
                    row = matched_slice.iloc[-1]

                    custom_data = {}
                    for k, s_val in custom_series.items():
                        try:
                            val = s_val.loc[ts] if ts in s_val.index else s_val.iloc[-1]
                            if isinstance(val, pd.Series):
                                val = val.iloc[-1]
                            if hasattr(val, 'item'):
                                val = val.item()
                            custom_data[k] = round(val, 2) if isinstance(val, (float, np.floating)) else val
                        except Exception:
                            custom_data[k] = '-'

                    idx_pos = len(matched_slice) - 1
                    pct_change = 0.0
                    if idx_pos > 0:
                        prev_row = matched_slice.iloc[idx_pos - 1]
                        if prev_row['Close'] > 0:
                            pct_change = ((row['Close'] - prev_row['Close']) / prev_row['Close'] * 100)

                    if not custom_data.get("R2_Cross_Date") or custom_data.get("R2_Cross_Date") == '-':
                        custom_data["R2_Cross_Date"] = compute_r2_cross_date_fallback(df_symbol, date_str)

                    res_item = {
                        "Date": date_str,
                        "Symbol": symbol,
                        "Close": float(row['Close']),
                        "Pct_Change": round(float(pct_change), 2),
                        "Volume": int(row['Volume']),
                        "Market_Cap_Cr": round(float(mcap_cr), 2) if mcap_cr else 0.0,
                        "custom_data": custom_data
                    }

                    if date_str not in historical_results:
                        historical_results[date_str] = []
                    historical_results[date_str].append(res_item)
                    total_matches += 1

        except Exception as e:
            error_count += 1
            last_error = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error screening symbol {symbol}: {e}")

    duration = time.time() - start_time
    logger.info(f"Screening complete. Found {total_matches} matches in {duration:.2f} seconds.")

    # If all symbols threw runtime errors, return actionable feedback
    if total_matches == 0 and error_count == len(symbols) and error_count > 0:
        return {
            "status": "error",
            "message": f"Execution error in screen(df): {last_error}",
            "timeframe": timeframe,
            "total_matches": 0,
            "flat_matches": []
        }

    # Flatten list sorted by date descending then symbol
    flat_matches = []
    for d_str in sorted(historical_results.keys(), reverse=True):
        for item in historical_results[d_str]:
            flat_matches.append(item)

    return {
        "status": "success",
        "timeframe": timeframe,
        "total_matches": total_matches,
        "total_symbols_scanned": len(symbols),
        "duration_seconds": round(duration, 2),
        "historical_results": historical_results,
        "flat_matches": flat_matches,
        "dates_with_matches": len(historical_results)
    }

# --- Strategies Storage ---

DEFAULT_STRATEGIES = [
    {
        "name": "EMA Crossover with Volume Filter",
        "code": """import pandas as pd

def screen(df):
    df = df.copy()
    
    # 1. Compute Indicators
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    
    # 2. Generate Crossover Signals
    # Close crosses above SMA20
    prev_close = df['Close'].shift(1)
    prev_sma20 = df['SMA20'].shift(1)
    crossover = (prev_close <= prev_sma20) & (df['Close'] > df['SMA20'])
    
    # Close is above EMA50
    above_ema = df['Close'] > df['EMA50']
    
    # 3. Return Boolean Series for historical backtesting
    signal = crossover & above_ema
    return {
        "signal": signal,
        "EMA50": df['EMA50'].round(2),
        "SMA20": df['SMA20'].round(2)
    }"""
    },
    {
        "name": "Monthly Pivot R2 Breakout",
        "code": """import pandas as pd

def screen(df):
    df = df.copy()
    df['Date_dt'] = pd.to_datetime(df['Date'])
    df['Month'] = df['Date_dt'].dt.to_period('M')

    # --- Step 1: Compute previous month's High, Low, Close for pivot calc ---
    monthly = df.groupby('Month').agg(
        High=('High', 'max'),
        Low=('Low', 'min'),
        Close=('Close', 'last')
    ).reset_index()

    # Shift by 1 so each month uses PREVIOUS month's H/L/C
    monthly['Prev_High'] = monthly['High'].shift(1)
    monthly['Prev_Low'] = monthly['Low'].shift(1)
    monthly['Prev_Close'] = monthly['Close'].shift(1)

    # --- Step 2: Standard pivot formulas ---
    monthly['Pivot'] = (monthly['Prev_High'] + monthly['Prev_Low'] + monthly['Prev_Close']) / 3
    monthly['R1'] = 2 * monthly['Pivot'] - monthly['Prev_Low']
    monthly['R2'] = monthly['Pivot'] + (monthly['Prev_High'] - monthly['Prev_Low'])

    # --- Step 3: Map monthly pivot levels back onto each daily row ---
    df = df.merge(monthly[['Month', 'Pivot', 'R1', 'R2']], on='Month', how='left')

    # --- Step 4: Detect Close crossing above R2 ---
    prev_close = df['Close'].shift(1)
    crossed_above_r2 = (prev_close <= df['R2']) & (df['Close'] > df['R2'])

    # --- Step 5: High volume filter (volume > 1.5x its 20-period average) ---
    avg_volume_20 = df['Volume'].rolling(window=20, min_periods=1).mean()
    high_volume = df['Volume'] > (1.5 * avg_volume_20)

    # --- Step 6: Combine conditions ---
    signal = crossed_above_r2 & high_volume

    return {
        "signal": signal
    }"""
    }
]

def load_strategies_from_file():
    if os.path.exists(STRATEGIES_FILE) and os.path.getsize(STRATEGIES_FILE) > 0:
        try:
            with open(STRATEGIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading strategies: {e}")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_STRATEGIES, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving default strategies: {e}")
    return DEFAULT_STRATEGIES

def save_strategy(name, code):
    name = name.strip()
    if not name or not code:
        return False

    strategies = load_strategies_from_file()
    found = False
    for s in strategies:
        if s['name'].lower() == name.lower():
            s['name'] = name
            s['code'] = code
            found = True
            break

    if not found:
        strategies.append({"name": name, "code": code})

    try:
        with open(STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(strategies, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Failed to save strategy: {e}")
        return False

def delete_strategy(name):
    strategies = load_strategies_from_file()
    clean_target = str(name).strip().lower()
    updated = [s for s in strategies if str(s.get('name', '')).strip().lower() != clean_target]
    if len(updated) == len(strategies):
        return False
    try:
        with open(STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(updated, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Failed to delete strategy: {e}")
        return False
# --- Backtest Strategies Storage & Engine ---

DEFAULT_BACKTEST_STRATEGIES = [
    {
        "name": "EMA 20/50 Crossover (TP 4% / SL 2%)",
        "code": """import pandas as pd
import numpy as np

def backtest(df):
    \"\"\"
    Backtest Strategy: EMA 20/50 Golden Cross
    Requirements:
      - long_entry: Boolean Series indicating entry signals
      - tp_pct: Target Profit percentage (e.g. 0.04 for 4% profit)
      - sl_pct: Stop Loss percentage (e.g. 0.02 for 2% risk)
    \"\"\"
    df = df.copy()
    
    # 1. Indicators
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    # 2. Long Entry Rule: EMA20 crosses above EMA50
    prev_ema20 = df['EMA20'].shift(1)
    prev_ema50 = df['EMA50'].shift(1)
    long_entry = (prev_ema20 <= prev_ema50) & (df['EMA20'] > df['EMA50'])
    
    # 3. Long Exit Rules: Target Profit and Stop Loss
    tp_pct = 0.04   # 4% Target Profit
    sl_pct = 0.02   # 2% Stop Loss
    
    return {
        "long_entry": long_entry,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct
    }"""
    },
    {
        "name": "Monthly R2 Breakout (TP 5% / SL 2.5%)",
        "code": """import pandas as pd
import numpy as np

def backtest(df):
    \"\"\"
    Backtest Strategy: Monthly Pivot R2 Breakout with High Volume
    \"\"\"
    df = df.copy()
    df['Date_dt'] = pd.to_datetime(df['Date'])
    df['Month'] = df['Date_dt'].dt.to_period('M')

    monthly = df.groupby('Month').agg(
        High=('High', 'max'),
        Low=('Low', 'min'),
        Close=('Close', 'last')
    ).reset_index()

    monthly['Prev_High'] = monthly['High'].shift(1)
    monthly['Prev_Low'] = monthly['Low'].shift(1)
    monthly['Prev_Close'] = monthly['Close'].shift(1)

    monthly['Pivot'] = (monthly['Prev_High'] + monthly['Prev_Low'] + monthly['Prev_Close']) / 3
    monthly['R2'] = monthly['Pivot'] + (monthly['Prev_High'] - monthly['Prev_Low'])

    df = df.merge(monthly[['Month', 'Pivot', 'R2']], on='Month', how='left')

    prev_close = df['Close'].shift(1)
    crossed_r2 = (prev_close <= df['R2']) & (df['Close'] > df['R2'])
    avg_vol = df['Volume'].rolling(window=20, min_periods=1).mean()
    high_vol = df['Volume'] > (1.3 * avg_vol)

    long_entry = crossed_r2 & high_vol
    tp_pct = 0.05   # 5% Target Profit
    sl_pct = 0.025  # 2.5% Stop Loss

    return {
        "long_entry": long_entry,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct
    }"""
    },
    {
        "name": "RSI Oversold Momentum Reversal (TP 6% / SL 3%)",
        "code": """import pandas as pd
import numpy as np

def backtest(df):
    \"\"\"
    Backtest Strategy: RSI (14) Pullback Reversal
    \"\"\"
    df = df.copy()
    
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    
    sma50 = df['Close'].rolling(50).mean()
    prev_rsi = df['RSI'].shift(1)
    rsi_reversal = (prev_rsi <= 35) & (df['RSI'] > 35)
    trend_filter = df['Close'] > sma50
    
    long_entry = rsi_reversal & trend_filter
    tp_pct = 0.06   # 6% Target Profit
    sl_pct = 0.03   # 3% Stop Loss
    
    return {
        "long_entry": long_entry,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct
    }"""
    }
]

def load_backtest_strategies_from_file():
    if os.path.exists(BACKTEST_STRATEGIES_FILE) and os.path.getsize(BACKTEST_STRATEGIES_FILE) > 0:
        try:
            with open(BACKTEST_STRATEGIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading backtest strategies: {e}")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(BACKTEST_STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_BACKTEST_STRATEGIES, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving default backtest strategies: {e}")
    return DEFAULT_BACKTEST_STRATEGIES

def save_backtest_strategy(name, code):
    name = name.strip()
    if not name or not code:
        return False
    strategies = load_backtest_strategies_from_file()
    found = False
    for s in strategies:
        if s['name'].lower() == name.lower():
            s['name'] = name
            s['code'] = code
            found = True
            break
    if not found:
        strategies.append({"name": name, "code": code})
    try:
        with open(BACKTEST_STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(strategies, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Failed to save backtest strategy: {e}")
        return False

def delete_backtest_strategy(name):
    strategies = load_backtest_strategies_from_file()
    clean_target = str(name).strip().lower()
    updated = [s for s in strategies if str(s.get('name', '')).strip().lower() != clean_target]
    if len(updated) == len(strategies):
        return False
    try:
        with open(BACKTEST_STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(updated, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Failed to delete backtest strategy: {e}")
        return False

def validate_backtest_code(code_str):
    """
    Validates that the backtest code:
    1. Compiles properly.
    2. Defines a callable function (backtest or strategy or screen).
    3. Explicitly specifies and returns Long Entry.
    4. Explicitly specifies and returns Target Profit (TP).
    5. Explicitly specifies and returns Stop Loss (SL).
    """
    if not code_str or not code_str.strip():
        return False, "Strategy code is empty. Please enter Python backtest logic.", None

    exec_env = {
        '__builtins__': __builtins__,
        'pd': pd,
        'np': np,
        'yf': yf,
        'datetime': datetime,
        'timedelta': timedelta,
        'get_market_cap_cr': get_market_cap_cr,
        'get_stock_fundamentals': get_stock_fundamentals,
        'get_fundamentals': get_stock_fundamentals,
        'get_stock_statement': get_stock_statement,
        'load_fundamentals_cache': load_fundamentals_cache,
    }

    try:
        exec(code_str, exec_env)
    except Exception as e:
        return False, f"Compile Error: {type(e).__name__}: {str(e)}", None

    func = None
    func_name = None
    for name in ['backtest', 'strategy', 'screen']:
        if name in exec_env and callable(exec_env[name]):
            func = exec_env[name]
            func_name = name
            break

    if not func:
        return False, "Function Missing: Strategy must define a callable function named 'backtest(df)'", None

    # Dry-run validation with dummy OHLCV data
    dates = pd.date_range('2024-01-01', periods=80, freq='D')
    dummy_df = pd.DataFrame({
        'Date': dates.strftime('%Y-%m-%d'),
        'Open': np.linspace(100, 140, 80),
        'High': np.linspace(102, 142, 80),
        'Low': np.linspace(98, 138, 80),
        'Close': np.linspace(101, 141, 80),
        'Volume': np.full(80, 100000),
        'Market_Cap_Cr': np.full(80, 5000.0)
    })
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Date']:
        dummy_df[col.lower()] = dummy_df[col]

    try:
        res = func(dummy_df.copy())
    except Exception as e:
        return False, f"Dry-run execution error in {func_name}(df): {type(e).__name__}: {str(e)}", None

    if not isinstance(res, dict):
        return False, "Validation Error: Strategy must return a dictionary containing 'long_entry', 'tp_pct' (or target_profit), and 'sl_pct' (or stop_loss).", None

    has_entry = any(k in res and res[k] is not None for k in ['long_entry', 'entry', 'entries', 'buy_signal', 'signal'])
    if not has_entry:
        return False, "Validation Error: Long Entry condition is missing. You must define and return 'long_entry' in your strategy dictionary.", None

    has_tp = any(k in res and res[k] is not None for k in ['tp_pct', 'target_profit_pct', 'tp', 'target_profit', 'target_pct'])
    if not has_tp:
        return False, "Validation Error: Target Profit (TP) is missing. Please define TP (e.g. tp_pct = 0.04 or 'tp_pct': 0.04 in return dict).", None

    has_sl = any(k in res and res[k] is not None for k in ['sl_pct', 'stop_loss_pct', 'sl', 'stop_loss', 'stop_pct'])
    if not has_sl:
        return False, "Validation Error: Stop Loss (SL) is missing. Please define SL (e.g. sl_pct = 0.02 or 'sl_pct': 0.02 in return dict).", None

    return True, None, func

def parse_date_flexible(d_str):
    """
    Safely parses various date formats into a datetime object.
    Supports '%Y-%m-%d', '%d-%b-%Y', '%d-%B-%Y', '%d-%m-%Y', ISO, and intraday timestamps.
    """
    if not d_str or str(d_str).strip() in ['-', 'None', 'nan', '', 'null', 'undefined']:
        return None
    s = str(d_str).strip()
    for fmt in (
        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
        '%d-%b-%Y %H:%M:%S', '%d-%b-%Y %H:%M', '%d-%b-%Y',
        '%d-%B-%Y %H:%M:%S', '%d-%B-%Y %H:%M', '%d-%B-%Y',
        '%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M', '%d-%m-%Y',
        '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y/%m/%d',
        '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'
    ):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    try:
        ts = pd.to_datetime(s)
        if pd.notna(ts):
            return ts.to_pydatetime()
    except Exception:
        pass
    return None

def format_date_dd_mmm_yyyy(d_str):
    """
    Formats a date string or datetime object to standard 'DD-MMM-YYYY' (e.g. '15-Jan-2024').
    If meaningful intraday time is present (non-zero), appends ' HH:MM'.
    """
    if not d_str or str(d_str).strip() in ['-', 'None', 'nan', '', 'null', 'undefined']:
        return '-'
    if isinstance(d_str, datetime):
        dt = d_str
    else:
        dt = parse_date_flexible(d_str)
    if not dt:
        return str(d_str)
    if dt.hour != 0 or dt.minute != 0 or dt.second != 0:
        return dt.strftime('%d-%b-%Y %H:%M')
    return dt.strftime('%d-%b-%Y')

def compute_backtest_analytics(trades, slippage_pct=0.5, include_brokerage=True, include_taxes=True, brokerage_per_order=20.0, weekday_filter=None, capital_per_trade=100000.0, month_filter=None):
    """
    Computes professional institutional backtest performance analytics:
    - 4-column Overall Performance Report with Risk-Adjusted Returns & Capital Exposure
    - Year-wise & Month-wise Returns matrix
    - Underwater Drawdown series
    - Brokerage, taxes, slippage adjustments
    """
    if not trades:
        return {
            "trades": [],
            "overall_report": {
                "overall_profit": 0.0,
                "no_of_trades": 0,
                "open_trades": 0,
                "avg_profit_per_trade": 0.0,
                "win_pct": 0.0,
                "loss_pct": 0.0,
                "avg_profit_on_winning": 0.0,
                "avg_loss_on_losing": 0.0,
                "max_profit_single": 0.0,
                "max_loss_single": 0.0,
                "max_drawdown": 0.0,
                "duration_of_max_drawdown": "-",
                "return_over_max_dd": 0.0,
                "reward_to_risk_ratio": 0.0,
                "expectancy_ratio": 0.0,
                "max_win_streak": 0,
                "max_losing_streak": 0,
                "max_trades_in_drawdown": 0,
                "profit_factor": 0.0,
                "cagr_pct": 0.0,
                "calmar_ratio": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_concurrent_positions": 0,
                "peak_capital_deployed": 0.0,
                "capital_utilization_pct": 0.0,
                "symbol_concentration_pct": 0.0,
                "symbol_concentration_str": "-",
                "symbol_concentration_details": "-",
                "avg_mae_pct": 0.0,
                "avg_mfe_pct": 0.0,
                "profitable_months_pct": 0.0,
                "profitable_months_str": "-",
                "green_months": 0,
                "red_months": 0,
                "avg_holding_win_days": 0.0,
                "avg_holding_loss_days": 0.0,
                "avg_holding_str": "-"
            },
            "year_wise_returns": [],
            "drawdown_chart": {"dates": [], "drawdowns": []},
            "summary": {
                "total_brokerage": 0.0,
                "total_taxes": 0.0,
                "slippage_pct": slippage_pct
            }
        }

    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    all_years = set()
    for t in trades:
        dt = parse_date_flexible(t.get('exit_date')) or parse_date_flexible(t.get('entry_date'))
        if dt:
            all_years.add(dt.year)

    filtered_trades = []
    for t in trades:
        if weekday_filter:
            t_wd = t.get('weekday', '')
            if t_wd and t_wd not in weekday_filter:
                continue
        if month_filter is not None:
            dt = parse_date_flexible(t.get('exit_date')) or parse_date_flexible(t.get('entry_date'))
            if dt:
                m_abbr = month_names[dt.month - 1]
                if m_abbr not in month_filter:
                    continue
        filtered_trades.append(t)

    if not filtered_trades:
        return compute_backtest_analytics([], slippage_pct, include_brokerage, include_taxes, brokerage_per_order)

    adjusted_trades = []
    for t in filtered_trades:
        t_copy = dict(t)
        # Check if trade is still running / End of Data across any strategy
        reason_str = str(t_copy.get('exit_reason', '')).strip().lower()
        is_running = (
            ('end of data' in reason_str) or
            ('end' in reason_str and 'data' in reason_str) or
            ('running' in reason_str) or
            bool(t_copy.get('is_open', False)) or
            (t_copy.get('net_pnl') is None and 'target' not in reason_str and 'stop' not in reason_str)
        )

        if is_running:
            t_copy['exit_reason'] = "End of Data"
            t_copy['turnover'] = None
            t_copy['gross_pnl'] = None
            t_copy['brokerage'] = None
            t_copy['taxes'] = None
            t_copy['net_pnl'] = None
            t_copy['pnl_pct'] = None
            t_copy['is_open'] = True
            adjusted_trades.append(t_copy)
            continue

        entry_p = float(t_copy['entry_price'])
        exit_p = float(t_copy['exit_price'])
        qty = int(t_copy['qty'])

        eff_entry = entry_p * (1.0 + slippage_pct / 100.0)
        eff_exit = exit_p * (1.0 - slippage_pct / 100.0)
        turnover = (eff_entry + eff_exit) * qty
        gross_pnl = (eff_exit - eff_entry) * qty
        brok = (brokerage_per_order * 2.0) if include_brokerage else 0.0
        tax = (turnover * 0.001 + (brok * 0.18)) if include_taxes else 0.0
        net_pnl = round(gross_pnl - brok - tax, 2)
        pnl_pct = round(((eff_exit - eff_entry) / eff_entry) * 100.0, 2)

        t_copy['turnover'] = round(turnover, 2)
        t_copy['gross_pnl'] = round(gross_pnl, 2)
        t_copy['brokerage'] = round(brok, 2)
        t_copy['taxes'] = round(tax, 2)
        t_copy['net_pnl'] = net_pnl
        t_copy['pnl_pct'] = pnl_pct
        t_copy['is_open'] = False
        adjusted_trades.append(t_copy)

    # Separate closed trades from open / running trades
    closed_trades = [t for t in adjusted_trades if not t.get('is_open') and t.get('net_pnl') is not None]
    open_trades = [t for t in adjusted_trades if t.get('is_open')]

    all_display_trades = sorted(adjusted_trades, key=lambda x: (parse_date_flexible(x.get('exit_date', '')) or datetime.min, parse_date_flexible(x.get('entry_date', '')) or datetime.min))

    if not closed_trades:
        return {
            "trades": all_display_trades,
            "overall_report": {
                "overall_profit": 0.0,
                "no_of_trades": 0,
                "open_trades": len(open_trades),
                "avg_profit_per_trade": 0.0,
                "win_trades": 0,
                "loss_trades": 0,
                "win_pct": 0.0,
                "loss_pct": 0.0,
                "avg_profit_on_winning": 0.0,
                "avg_loss_on_losing": 0.0,
                "max_profit_single": 0.0,
                "max_loss_single": 0.0,
                "max_drawdown": 0.0,
                "duration_of_max_drawdown": "-",
                "return_over_max_dd": 0.0,
                "reward_to_risk_ratio": 0.0,
                "expectancy_ratio": 0.0,
                "max_win_streak": 0,
                "max_losing_streak": 0,
                "max_trades_in_drawdown": 0,
                "profit_factor": 0.0,
                "cagr_pct": 0.0,
                "calmar_ratio": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_concurrent_positions": 0,
                "peak_capital_deployed": 0.0,
                "capital_utilization_pct": 0.0,
                "symbol_concentration_pct": 0.0,
                "symbol_concentration_str": "-",
                "symbol_concentration_details": "-",
                "avg_mae_pct": 0.0,
                "avg_mfe_pct": 0.0,
                "profitable_months_pct": 0.0,
                "profitable_months_str": "-",
                "green_months": 0,
                "red_months": 0,
                "avg_holding_win_days": 0.0,
                "avg_holding_loss_days": 0.0,
                "avg_holding_str": "-"
            },
            "year_wise_returns": [],
            "drawdown_chart": {"dates": [], "drawdowns": []},
            "summary": {
                "total_brokerage": 0.0,
                "total_taxes": 0.0,
                "slippage_pct": slippage_pct
            }
        }

    sorted_trades = sorted(closed_trades, key=lambda x: (parse_date_flexible(x.get('exit_date', '')) or datetime.min, parse_date_flexible(x.get('entry_date', '')) or datetime.min))
    total_trades = len(sorted_trades)
    pnls = [t['net_pnl'] for t in sorted_trades]
    overall_profit = round(sum(pnls), 2)
    avg_profit_per_trade = round(overall_profit / total_trades, 2)

    winning = [p for p in pnls if p > 0]
    losing = [p for p in pnls if p < 0]
    win_pct = round((len(winning) / total_trades) * 100, 2)
    loss_pct = round((len(losing) / total_trades) * 100, 2)
    avg_profit_on_winning = round(sum(winning) / len(winning), 2) if winning else 0.0
    avg_loss_on_losing = round(sum(losing) / len(losing), 2) if losing else 0.0
    max_profit_single = round(max(pnls), 2) if pnls else 0.0
    max_loss_single = round(min(pnls), 2) if pnls else 0.0

    reward_to_risk = round(abs(avg_profit_on_winning / avg_loss_on_losing), 2) if avg_loss_on_losing != 0 else 0.0
    if avg_loss_on_losing != 0:
        expectancy = round(((win_pct / 100.0 * avg_profit_on_winning) - (loss_pct / 100.0 * abs(avg_loss_on_losing))) / abs(avg_loss_on_losing), 2)
    else:
        expectancy = 0.0

    # Streaks
    max_win_streak = 0
    curr_win = 0
    max_lose_streak = 0
    curr_lose = 0
    for p in pnls:
        if p > 0:
            curr_win += 1
            curr_lose = 0
            if curr_win > max_win_streak:
                max_win_streak = curr_win
        elif p < 0:
            curr_lose += 1
            curr_win = 0
            if curr_lose > max_lose_streak:
                max_lose_streak = curr_lose
        else:
            curr_win = 0
            curr_lose = 0

    # Drawdown Curve
    cum_equity = 0.0
    peak = 0.0
    peak_date = sorted_trades[0]['exit_date']
    
    overall_max_dd = 0.0
    mdd_peak_date = peak_date
    mdd_trough_date = peak_date
    
    chart_dates = []
    chart_drawdowns = []
    
    trades_in_curr_dd = 0
    max_trades_in_dd = 0

    for t in sorted_trades:
        cum_equity += t['net_pnl']
        exit_dt = t['exit_date']
        
        if cum_equity >= peak:
            peak = cum_equity
            peak_date = exit_dt
            dd = 0.0
            trades_in_curr_dd = 0
        else:
            dd = cum_equity - peak
            trades_in_curr_dd += 1
            if trades_in_curr_dd > max_trades_in_dd:
                max_trades_in_dd = trades_in_curr_dd
            
            if dd < overall_max_dd:
                overall_max_dd = dd
                mdd_peak_date = peak_date
                mdd_trough_date = exit_dt

        chart_dates.append(format_date_dd_mmm_yyyy(exit_dt))
        chart_drawdowns.append(round(dd, 2))

    try:
        p_dt = parse_date_flexible(mdd_peak_date)
        t_dt = parse_date_flexible(mdd_trough_date)
        mdd_days = max(1, abs((t_dt - p_dt).days)) if (overall_max_dd < 0 and p_dt and t_dt) else 0
        p_dt_str = format_date_dd_mmm_yyyy(mdd_peak_date)
        t_dt_str = format_date_dd_mmm_yyyy(mdd_trough_date)
    except Exception:
        mdd_days = 0
        p_dt_str = "-"
        t_dt_str = "-"
        
    duration_of_mdd = f"{mdd_days} [{p_dt_str} to {t_dt_str}]" if overall_max_dd < 0 else "-"
    return_over_max_dd = round(overall_profit / abs(overall_max_dd), 2) if overall_max_dd < 0 else 0.0

    total_brok = round(sum(t['brokerage'] for t in sorted_trades if t.get('brokerage') is not None), 2)
    total_tax = round(sum(t['taxes'] for t in sorted_trades if t.get('taxes') is not None), 2)

    # -----------------------------------------------------------------
    # Capital, Timeline & Max Concurrent Open Positions
    # -----------------------------------------------------------------
    all_trade_intervals = []
    for t in adjusted_trades:
        try:
            d_in = parse_date_flexible(t.get('entry_date'))
            d_out = parse_date_flexible(t.get('exit_date'))
            if d_in and d_out:
                all_trade_intervals.append((d_in, d_out, t))
        except Exception:
            continue

    max_concurrent_positions = 1
    peak_capital_deployed = float(capital_per_trade)
    avg_capital_utilization = 0.0
    span_years = 1.0

    if all_trade_intervals:
        min_date = min(x[0] for x in all_trade_intervals)
        max_date = max(x[1] for x in all_trade_intervals)
        span_years = max(0.0833, (max_date - min_date).days / 365.25)

        # Timeline event sweep
        events = []
        for d_in, d_out, _ in all_trade_intervals:
            events.append((d_in, 1))
            events.append((d_out + timedelta(days=1), -1))
        events.sort(key=lambda x: (x[0], -x[1]))

        curr_pos = 0
        max_pos = 0
        for ev_dt, change in events:
            curr_pos += change
            if curr_pos > max_pos:
                max_pos = curr_pos

        max_concurrent_positions = max(1, max_pos)
        peak_capital_deployed = round(max_concurrent_positions * capital_per_trade, 2)

        # Capital utilization over active calendar span
        curr_p = 0
        ev_idx = 0
        daily_p_list = []
        curr_day = min_date
        while curr_day <= max_date:
            while ev_idx < len(events) and events[ev_idx][0] <= curr_day:
                curr_p += events[ev_idx][1]
                ev_idx += 1
            daily_p_list.append(curr_p)
            curr_day += timedelta(days=1)

        if daily_p_list and max_concurrent_positions > 0:
            avg_capital_utilization = round((float(np.mean(daily_p_list)) / max_concurrent_positions) * 100.0, 2)
        else:
            avg_capital_utilization = 0.0

    base_capital = max(peak_capital_deployed, capital_per_trade)

    # Year-wise & Month-wise Returns Matrix
    years_dict = {
        yr: {
            "year": yr,
            "months": {m: 0.0 for m in month_names},
            "trades": []
        }
        for yr in sorted(all_years)
    }
    
    for t in sorted_trades:
        dt = parse_date_flexible(t.get('exit_date')) or parse_date_flexible(t.get('entry_date'))
        if not dt:
            continue
        yr = dt.year
        m_idx = dt.month - 1
            
        if yr not in years_dict:
            years_dict[yr] = {
                "year": yr,
                "months": {m: 0.0 for m in month_names},
                "trades": []
            }
        years_dict[yr]["months"][month_names[m_idx]] += t['net_pnl']
        years_dict[yr]["trades"].append(t)

    year_wise_rows = []
    for yr in sorted(years_dict.keys()):
        yr_info = years_dict[yr]
        m_vals = {m: round(yr_info["months"][m], 2) for m in month_names}
        yr_total = round(sum(m_vals.values()), 2)
        
        yr_cum = 0.0
        yr_peak = 0.0
        yr_max_dd = 0.0
        
        if yr_info["trades"]:
            yr_peak_dt = yr_info["trades"][0]['exit_date']
            yr_trough_dt = yr_peak_dt
            
            for tr in yr_info["trades"]:
                yr_cum += tr['net_pnl']
                if yr_cum >= yr_peak:
                    yr_peak = yr_cum
                    yr_peak_dt = tr['exit_date']
                else:
                    curr_dd = yr_cum - yr_peak
                    if curr_dd < yr_max_dd:
                        yr_max_dd = curr_dd
                        yr_trough_dt = tr['exit_date']
                        
            try:
                yd_p = parse_date_flexible(yr_peak_dt)
                yd_t = parse_date_flexible(yr_trough_dt)
                yr_days = max(1, abs((yd_t - yd_p).days)) if (yr_max_dd < 0 and yd_p and yd_t) else 0
                yd_p_str = format_date_dd_mmm_yyyy(yr_peak_dt)
                yd_t_str = format_date_dd_mmm_yyyy(yr_trough_dt)
            except Exception:
                yr_days = 0
                yd_p_str = "-"
                yd_t_str = "-"
                
            yr_days_str = f"{yr_days} [{yd_p_str} to {yd_t_str}]" if yr_max_dd < 0 else "-"
            yr_r_mdd = round(yr_total / abs(yr_max_dd), 2) if yr_max_dd < 0 else (round(yr_total, 2) if yr_total != 0 else 0.0)
        else:
            yr_max_dd = 0.0
            yr_days_str = "-"
            yr_r_mdd = 0.0

        yr_cagr = round((yr_total / base_capital) * 100.0, 2) if base_capital > 0 else 0.0

        row = {
            "year": yr,
            **m_vals,
            "total": yr_total,
            "max_drawdown": round(yr_max_dd, 2),
            "days_for_mdd": yr_days_str,
            "r_mdd": yr_r_mdd,
            "cagr": yr_cagr
        }
        year_wise_rows.append(row)

    # -----------------------------------------------------------------
    # Advanced Institutional & Risk-Adjusted Analytics (10 Metrics)
    # -----------------------------------------------------------------
    # 1. Profit Factor (Gross Profit ÷ Gross Loss)
    gross_winning = sum(p for p in pnls if p > 0)
    gross_losing = abs(sum(p for p in pnls if p < 0))
    if gross_losing > 0:
        profit_factor = round(gross_winning / gross_losing, 2)
    elif gross_winning > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0

    # 3. CAGR / Annualized Return % (Based on peak capital deployed)
    total_ret_ratio = overall_profit / base_capital if base_capital > 0 else 0.0
    if (1.0 + total_ret_ratio) > 0:
        cagr_pct = round(((1.0 + total_ret_ratio) ** (1.0 / span_years) - 1.0) * 100.0, 2)
    else:
        cagr_pct = -100.0

    # 4. Calmar Ratio (CAGR ÷ Max DD %)
    max_dd_pct = (abs(overall_max_dd) / base_capital) * 100.0 if base_capital > 0 else 0.0
    if max_dd_pct > 0:
        calmar_ratio = round(cagr_pct / max_dd_pct, 2)
    else:
        calmar_ratio = round(cagr_pct, 2) if cagr_pct > 0 else 0.0

    # 5. Sharpe & Sortino Ratio (Monthly excess returns over 6% risk-free rate)
    monthly_ret_list = []
    for r in year_wise_rows:
        for m in month_names:
            val = r.get(m, 0.0)
            monthly_ret_list.append(val / base_capital if base_capital > 0 else 0.0)

    if monthly_ret_list and len(monthly_ret_list) > 1:
        rf_monthly = 0.06 / 12.0
        excess_ret = [rm - rf_monthly for rm in monthly_ret_list]
        mean_excess = float(np.mean(excess_ret))
        std_monthly = float(np.std(monthly_ret_list, ddof=1))

        sharpe_ratio = round(float(np.sqrt(12) * (mean_excess / std_monthly)), 2) if std_monthly > 0 else 0.0

        downside = [min(0.0, rm - rf_monthly) for rm in monthly_ret_list]
        downside_dev = float(np.sqrt(np.mean([d ** 2 for d in downside])))
        sortino_ratio = round(float(np.sqrt(12) * (mean_excess / downside_dev)), 2) if downside_dev > 0 else 0.0
    else:
        sharpe_ratio = 0.0
        sortino_ratio = 0.0

    # 6. Symbol Concentration (Top 5 Stocks)
    sym_profit_map = {}
    for t in sorted_trades:
        sym = t.get('symbol', 'Other')
        sym_profit_map[sym] = sym_profit_map.get(sym, 0.0) + t['net_pnl']

    sorted_syms = sorted(sym_profit_map.items(), key=lambda x: x[1], reverse=True)
    top5_syms = sorted_syms[:5]
    top5_profit = sum(p for _, p in top5_syms if p > 0)
    if overall_profit > 0 and top5_profit > 0:
        top5_pct = round((top5_profit / overall_profit) * 100.0, 1)
        top_tickers_str = ", ".join(f"{s} ({round((p / overall_profit) * 100, 1)}%)" for s, p in top5_syms if p > 0)
        symbol_concentration_str = f"Top 5: {top5_pct}%"
        symbol_concentration_details = top_tickers_str
    else:
        top5_pct = 0.0
        symbol_concentration_str = "-"
        symbol_concentration_details = "-"

    # 7. MAE / MFE (Max Adverse / Favorable Excursion)
    maes = [float(t['mae_pct']) for t in sorted_trades if t.get('mae_pct') is not None]
    mfes = [float(t['mfe_pct']) for t in sorted_trades if t.get('mfe_pct') is not None]
    avg_mae = round(float(np.mean(maes)), 2) if maes else 0.0
    avg_mfe = round(float(np.mean(mfes)), 2) if mfes else 0.0

    # 8. % Profitable Months (Green vs Red months)
    active_m_pnls = []
    for yr_info in years_dict.values():
        for m in month_names:
            pnl_m = yr_info["months"][m]
            target_month = month_names.index(m) + 1
            has_trades = any(
                (parse_date_flexible(t.get('exit_date')).year == yr_info['year'] and parse_date_flexible(t.get('exit_date')).month == target_month)
                for t in yr_info["trades"]
                if parse_date_flexible(t.get('exit_date'))
            )
            if has_trades or pnl_m != 0:
                active_m_pnls.append(pnl_m)

    green_months = sum(1 for p in active_m_pnls if p > 0)
    red_months = sum(1 for p in active_m_pnls if p < 0)
    tot_active_months = green_months + red_months
    profitable_months_pct = round((green_months / tot_active_months * 100.0), 1) if tot_active_months > 0 else 0.0
    profitable_months_str = f"{profitable_months_pct}% ({green_months}G / {red_months}R)"

    # 9. Avg Holding Period (Winners vs Losers)
    win_durations = []
    loss_durations = []
    for t in sorted_trades:
        dur = t.get('duration_days')
        if dur is None:
            try:
                d1 = parse_date_flexible(t.get('entry_date'))
                d2 = parse_date_flexible(t.get('exit_date'))
                dur = max(0, (d2 - d1).days) if (d1 and d2) else 0
            except Exception:
                dur = 0
        if t['net_pnl'] > 0:
            win_durations.append(dur)
        elif t['net_pnl'] < 0:
            loss_durations.append(dur)

    avg_holding_win = round(float(np.mean(win_durations)), 1) if win_durations else 0.0
    avg_holding_loss = round(float(np.mean(loss_durations)), 1) if loss_durations else 0.0
    avg_holding_str = f"Win: {avg_holding_win}d | Loss: {avg_holding_loss}d"

    formatted_display_trades = []
    for t in all_display_trades:
        t_copy = dict(t)
        if t_copy.get('trigger_date') and str(t_copy['trigger_date']) not in ['-', 'None', 'nan', '']:
            t_copy['trigger_date'] = format_date_dd_mmm_yyyy(t_copy['trigger_date'])
        if t_copy.get('entry_date'):
            t_copy['entry_date'] = format_date_dd_mmm_yyyy(t_copy['entry_date'])
        if t_copy.get('exit_date'):
            t_copy['exit_date'] = format_date_dd_mmm_yyyy(t_copy['exit_date'])
        formatted_display_trades.append(t_copy)

    return {
        "trades": formatted_display_trades,
        "overall_report": {
            "overall_profit": overall_profit,
            "no_of_trades": total_trades,
            "open_trades": len(open_trades),
            "avg_profit_per_trade": avg_profit_per_trade,
            "win_trades": len(winning),
            "loss_trades": len(losing),
            "win_pct": win_pct,
            "loss_pct": loss_pct,
            "avg_profit_on_winning": avg_profit_on_winning,
            "avg_loss_on_losing": avg_loss_on_losing,
            "max_profit_single": max_profit_single,
            "max_loss_single": max_loss_single,
            "max_drawdown": round(overall_max_dd, 2),
            "duration_of_max_drawdown": duration_of_mdd,
            "return_over_max_dd": return_over_max_dd,
            "reward_to_risk_ratio": reward_to_risk,
            "expectancy_ratio": expectancy,
            "max_win_streak": max_win_streak,
            "max_losing_streak": max_lose_streak,
            "max_trades_in_drawdown": max_trades_in_dd,
            # Institutional & Risk-Adjusted Metrics
            "profit_factor": profit_factor,
            "cagr_pct": cagr_pct,
            "calmar_ratio": calmar_ratio,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_concurrent_positions": max_concurrent_positions,
            "peak_capital_deployed": peak_capital_deployed,
            "capital_utilization_pct": avg_capital_utilization,
            "symbol_concentration_pct": top5_pct,
            "symbol_concentration_str": symbol_concentration_str,
            "symbol_concentration_details": symbol_concentration_details,
            "avg_mae_pct": avg_mae,
            "avg_mfe_pct": avg_mfe,
            "profitable_months_pct": profitable_months_pct,
            "profitable_months_str": profitable_months_str,
            "green_months": green_months,
            "red_months": red_months,
            "avg_holding_win_days": avg_holding_win,
            "avg_holding_loss_days": avg_holding_loss,
            "avg_holding_str": avg_holding_str
        },
        "year_wise_returns": year_wise_rows,
        "drawdown_chart": {
            "dates": chart_dates,
            "drawdowns": chart_drawdowns
        },
        "summary": {
            "total_brokerage": total_brok,
            "total_taxes": total_tax,
            "slippage_pct": slippage_pct
        }
    }

def run_backtest_simulation(code_str, segment, timeframe='1d', watchlist_symbols=None, start_date=None, end_date=None, capital_per_trade=100000.0, slippage_pct=0.5, include_brokerage=True, include_taxes=True, brokerage_per_order=20.0, min_market_cap_cr=2000.0):
    """
    Executes a realistic bar-by-bar backtest simulation:
    - Pre-validates presence of Long Entry, TP, and SL
    - Simulates per-stock trades with exact entry and exit prices
    - Returns comprehensive trade logs, year-wise matrix, drawdown curve, and overall report
    """
    is_valid, err_msg, func = validate_backtest_code(code_str)
    if not is_valid:
        return {"status": "error", "message": err_msg}

    symbols = []
    if segment == 'nifty50':
        symbols = fetch_nifty50_symbols()
    elif segment == 'nifty500':
        symbols = fetch_nifty500_symbols()
    elif segment == 'fno':
        symbols = fetch_fno_symbols()
    elif segment == 'watchlist' and watchlist_symbols:
        symbols = watchlist_symbols
    else:
        symbols = get_available_parquet_symbols()
        if not symbols:
            db_df = load_database()
            if not db_df.empty:
                symbols = db_df['Symbol'].dropna().unique().tolist()

    start_time = time.time()
    logger.info(f"Running backtest on {len(symbols)} stocks on timeframe '{timeframe}'...")

    raw_trades = []
    trade_id = 1
    error_count = 0
    last_error = ""

    for symbol in symbols:
        mcap_cr = get_market_cap_cr(symbol, fetch_online=True)
        if min_market_cap_cr > 0 and mcap_cr > 0 and mcap_cr < min_market_cap_cr:
            continue

        # Fetch full history (up to end_date) so EMAs, rolling volume, and monthly pivots have complete warm-up data
        df_symbol = get_ticker_data_duckdb(symbol, timeframe=timeframe, start_date=None, end_date=end_date)
        if df_symbol.empty:
            continue

        # df_symbol is already corporate action adjusted (via pre-adjusted daily cache or get_ticker_data_duckdb)
        if timeframe not in ['1d', 'daily', 'day']:
            df_symbol = adjust_parquet_splits(df_symbol, symbol)
        if len(df_symbol) < 5:
            continue

        try:
            res = func(df_symbol.copy())
            if not isinstance(res, dict):
                continue

            # Support direct multi-state simulated trades from advanced strategies
            if 'trades' in res and isinstance(res['trades'], list):
                for tr in res['trades']:
                    entry_date_str = str(tr.get('entry_date', ''))[:10]
                    if start_date and entry_date_str:
                        start_dt_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, (datetime, pd.Timestamp)) else str(start_date)[:10]
                        if entry_date_str < start_dt_str:
                            continue

                    entry_price = float(tr['entry_price'])
                    exit_price = float(tr['exit_price'])
                    qty = max(1, int(capital_per_trade / entry_price))
                    ex_reason = str(tr.get('exit_reason', 'Exit'))
                    mae_val = float(tr.get('mae_pct', 0.0)) if tr.get('mae_pct') is not None else 0.0
                    mfe_val = float(tr.get('mfe_pct', 0.0)) if tr.get('mfe_pct') is not None else 0.0

                    try:
                        d_in = datetime.strptime(str(tr['entry_date'])[:10], '%Y-%m-%d')
                        d_out = datetime.strptime(str(tr['exit_date'])[:10], '%Y-%m-%d')
                        duration_days = (d_out - d_in).days
                        weekday_str = d_in.strftime('%a')
                    except Exception:
                        duration_days = 0
                        weekday_str = "Mon"

                    ex_clean = str(ex_reason).strip().lower()
                    is_eod = (
                        ('end of data' in ex_clean) or
                        ('end' in ex_clean and 'data' in ex_clean) or
                        ('running' in ex_clean) or
                        bool(tr.get('is_open', False))
                    )

                    if is_eod:
                        raw_trades.append({
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "type": "Long",
                            "trigger_date": str(tr.get('trigger_date', '-')),
                            "entry_date": str(tr['entry_date']),
                            "entry_price": round(entry_price, 2),
                            "exit_date": str(tr['exit_date']),
                            "exit_price": round(exit_price, 2),
                            "exit_reason": "End of Data",
                            "qty": qty,
                            "turnover": None,
                            "gross_pnl": None,
                            "brokerage": None,
                            "taxes": None,
                            "net_pnl": None,
                            "pnl_pct": None,
                            "duration": f"{duration_days}d (Running)" if duration_days > 0 else "Running",
                            "duration_days": duration_days,
                            "mae_pct": round(mae_val, 2),
                            "mfe_pct": round(mfe_val, 2),
                            "weekday": weekday_str,
                            "is_open": True
                        })
                    else:
                        eff_entry = entry_price * (1.0 + slippage_pct / 100.0)
                        eff_exit = exit_price * (1.0 - slippage_pct / 100.0)
                        turnover = (eff_entry + eff_exit) * qty
                        gross_pnl = (eff_exit - eff_entry) * qty
                        brok = (brokerage_per_order * 2.0) if include_brokerage else 0.0
                        tax = (turnover * 0.001 + (brok * 0.18)) if include_taxes else 0.0
                        net_pnl = gross_pnl - brok - tax
                        pnl_pct = ((eff_exit - eff_entry) / eff_entry) * 100.0

                        raw_trades.append({
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "type": "Long",
                            "trigger_date": str(tr.get('trigger_date', '-')),
                            "entry_date": str(tr['entry_date']),
                            "entry_price": round(entry_price, 2),
                            "exit_date": str(tr['exit_date']),
                            "exit_price": round(exit_price, 2),
                            "exit_reason": ex_reason,
                            "qty": qty,
                            "turnover": round(turnover, 2),
                            "gross_pnl": round(gross_pnl, 2),
                            "brokerage": round(brok, 2),
                            "taxes": round(tax, 2),
                            "net_pnl": round(net_pnl, 2),
                            "pnl_pct": round(pnl_pct, 2),
                            "duration": f"{duration_days}d" if duration_days > 0 else "Same Day",
                            "duration_days": duration_days,
                            "mae_pct": round(mae_val, 2),
                            "mfe_pct": round(mfe_val, 2),
                            "weekday": weekday_str,
                            "is_open": False
                        })
                    trade_id += 1
                continue

            entry_obj = None
            for k in ['long_entry', 'entries', 'buy_signal', 'signal']:
                if k in res and res[k] is not None:
                    entry_obj = res[k]
                    break

            tp_val = None
            for k in ['tp_pct', 'target_profit_pct', 'tp', 'target_profit', 'target_pct']:
                if k in res and res[k] is not None:
                    tp_val = res[k]
                    break

            sl_val = None
            for k in ['sl_pct', 'stop_loss_pct', 'sl', 'stop_loss', 'stop_pct']:
                if k in res and res[k] is not None:
                    sl_val = res[k]
                    break

            exit_signal_obj = None
            for k in ['exit_signal', 'exit', 'long_exit']:
                if k in res and res[k] is not None:
                    exit_signal_obj = res[k]
                    break

            stop_loss_obj = None
            for k in ['stop_loss', 'sl_signal', 'stop']:
                if k in res and res[k] is not None:
                    stop_loss_obj = res[k]
                    break

            trigger_date_obj = None
            for k in ['trigger_date', 'Trigger_Date', 'trigger_dates', 'buy_trigger_date', 'Buy_Trigger_Date']:
                if k in res and res[k] is not None:
                    trigger_date_obj = res[k]
                    break

            if entry_obj is None or tp_val is None or sl_val is None:
                continue

            tp_series = tp_val.values if hasattr(tp_val, 'values') else (np.array(tp_val) if isinstance(tp_val, (list, np.ndarray)) else None)
            sl_series = sl_val.values if hasattr(sl_val, 'values') else (np.array(sl_val) if isinstance(sl_val, (list, np.ndarray)) else None)

            # Fallback default scalar values
            tp_pct = 0.10
            if isinstance(tp_val, (int, float)):
                tp_pct = float(tp_val) if float(tp_val) < 1.0 else float(tp_val) / 100.0
            elif tp_series is not None:
                valid_tp = tp_series[~np.isnan(tp_series)]
                if len(valid_tp) > 0:
                    tp_pct = float(valid_tp[0]) if float(valid_tp[0]) < 1.0 else float(valid_tp[0]) / 100.0

            sl_pct = 0.05
            if isinstance(sl_val, (int, float)):
                sl_pct = float(sl_val) if float(sl_val) < 1.0 else float(sl_val) / 100.0
            elif sl_series is not None:
                valid_sl = sl_series[~np.isnan(sl_series)]
                if len(valid_sl) > 0:
                    sl_pct = float(valid_sl[0]) if float(valid_sl[0]) < 1.0 else float(valid_sl[0]) / 100.0

            # Support multi-timeframe / resampled strategies:
            # If strategy returned a resampled DataFrame or series matching entry_obj
            df_eval = df_symbol
            if 'df' in res and isinstance(res['df'], pd.DataFrame) and len(res['df']) == len(entry_obj):
                df_eval = res['df']
            elif 'hourly' in res and isinstance(res['hourly'], pd.DataFrame) and len(res['hourly']) == len(entry_obj):
                df_eval = res['hourly']
            elif hasattr(entry_obj, 'index') and len(entry_obj) != len(df_symbol):
                df_temp = df_symbol.copy()
                if not isinstance(df_temp.index, pd.DatetimeIndex):
                    if 'date' in df_temp.columns:
                        df_temp.index = pd.to_datetime(df_temp['date'])
                    elif 'Date' in df_temp.columns:
                        df_temp.index = pd.to_datetime(df_temp['Date'])
                if isinstance(entry_obj.index, pd.DatetimeIndex):
                    agg_dict = {'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}
                    if 'Volume' in df_temp.columns:
                        agg_dict['Volume'] = 'sum'
                    try:
                        df_res = df_temp.resample('1h', offset='15min').agg(agg_dict).dropna(subset=['Close'])
                        if len(df_res) == len(entry_obj):
                            df_eval = df_res
                            df_eval['Date'] = df_eval.index.strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        pass

            entries_bool = entry_obj.values if hasattr(entry_obj, 'values') else np.array(entry_obj)
            exit_signal_bool = (exit_signal_obj.values if hasattr(exit_signal_obj, 'values') else np.array(exit_signal_obj)) if exit_signal_obj is not None else None
            stop_loss_bool = (stop_loss_obj.values if hasattr(stop_loss_obj, 'values') else np.array(stop_loss_obj)) if stop_loss_obj is not None else None

            c_col = 'Close' if 'Close' in df_eval.columns else 'close'
            h_col = 'High' if 'High' in df_eval.columns else 'high'
            l_col = 'Low' if 'Low' in df_eval.columns else 'low'
            o_col = 'Open' if 'Open' in df_eval.columns else 'open'
            d_col = 'Date' if 'Date' in df_eval.columns else ('date' if 'date' in df_eval.columns else None)

            closes = df_eval[c_col].values
            highs = df_eval[h_col].values
            lows = df_eval[l_col].values
            opens = df_eval[o_col].values
            dates = df_eval[d_col].astype(str).values if d_col else df_eval.index.astype(str).values
            n = len(df_eval)

            in_trade = False
            entry_idx = -1
            entry_price = 0.0
            target_price = 0.0
            stop_price = 0.0
            qty = 0
            entry_dt = ""
            entry_trigger_dt = "-"

            for i in range(n):
                if not in_trade:
                    if entries_bool[i]:
                        if start_date:
                            start_dt_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, (datetime, pd.Timestamp)) else str(start_date)[:10]
                            if str(dates[i])[:10] < start_dt_str:
                                continue
                        in_trade = True
                        entry_idx = i
                        entry_price = float(closes[i])
                        entry_dt = dates[i]
                        qty = max(1, int(capital_per_trade / entry_price))

                        entry_trigger_dt = "-"
                        if trigger_date_obj is not None:
                            try:
                                if hasattr(trigger_date_obj, 'iloc'):
                                    td_val = trigger_date_obj.iloc[i]
                                elif hasattr(trigger_date_obj, '__getitem__'):
                                    td_val = trigger_date_obj[i]
                                else:
                                    td_val = str(trigger_date_obj)
                                if td_val is not None and str(td_val) not in ['nan', 'None', '-']:
                                    entry_trigger_dt = str(td_val)
                            except Exception:
                                pass
                        elif 'Trigger_Date' in df_eval.columns:
                            try:
                                td_val = df_eval['Trigger_Date'].iloc[i]
                                if td_val is not None and str(td_val) not in ['nan', 'None', '-']:
                                    entry_trigger_dt = str(td_val)
                            except Exception:
                                pass

                        this_tp = float(tp_series[i]) if (tp_series is not None and not np.isnan(tp_series[i])) else tp_pct
                        this_sl = float(sl_series[i]) if (sl_series is not None and not np.isnan(sl_series[i])) else sl_pct
                        if this_tp > 1.0:
                            this_tp /= 100.0
                        if this_sl > 1.0:
                            this_sl /= 100.0

                        target_price = round(entry_price * (1.0 + this_tp), 2)
                        stop_price = round(entry_price * (1.0 - this_sl), 2)
                else:
                    high_p = highs[i]
                    low_p = lows[i]
                    hit_tp = high_p >= target_price
                    hit_sl = low_p <= stop_price

                    exit_price = 0.0
                    exit_reason = ""
                    if hit_tp and hit_sl:
                        if opens[i] >= entry_price:
                            exit_price = target_price
                            exit_reason = "Target Profit (TP)"
                        else:
                            exit_price = stop_price
                            exit_reason = "Stop Loss (SL)"
                    elif hit_tp:
                        exit_price = target_price
                        exit_reason = "Target Profit (TP)"
                    elif hit_sl:
                        exit_price = stop_price
                        exit_reason = "Stop Loss (SL)"
                    elif exit_signal_bool is not None and exit_signal_bool[i]:
                        exit_price = float(closes[i])
                        is_sl = bool(stop_loss_bool is not None and i < len(stop_loss_bool) and stop_loss_bool[i])
                        exit_reason = "Stop Loss (SL)" if is_sl else "Exit Signal"
                    elif i == n - 1:
                        exit_price = float(closes[i])
                        exit_reason = "End of Data"

                    if exit_reason:
                        trade_lows = lows[entry_idx : i + 1]
                        trade_highs = highs[entry_idx : i + 1]
                        min_p = float(np.min(trade_lows)) if len(trade_lows) > 0 else entry_price
                        max_p = float(np.max(trade_highs)) if len(trade_highs) > 0 else entry_price
                        mae_pct = max(0.0, ((entry_price - min_p) / entry_price) * 100.0) if entry_price > 0 else 0.0
                        mfe_pct = max(0.0, ((max_p - entry_price) / entry_price) * 100.0) if entry_price > 0 else 0.0

                        try:
                            d_in = datetime.strptime(entry_dt[:10], '%Y-%m-%d')
                            d_out = datetime.strptime(dates[i][:10], '%Y-%m-%d')
                            duration_days = (d_out - d_in).days
                            weekday_str = d_in.strftime('%a')
                        except Exception:
                            duration_days = i - entry_idx
                            weekday_str = "Mon"

                        reason_clean = str(exit_reason).strip().lower()
                        is_eod = ('end of data' in reason_clean) or ('end' in reason_clean and 'data' in reason_clean) or ('running' in reason_clean)

                        if is_eod:
                            raw_trades.append({
                                "trade_id": trade_id,
                                "symbol": symbol,
                                "type": "Long",
                                "trigger_date": entry_trigger_dt,
                                "entry_date": entry_dt,
                                "entry_price": round(entry_price, 2),
                                "exit_date": dates[i],
                                "exit_price": round(exit_price, 2),
                                "exit_reason": "End of Data",
                                "qty": qty,
                                "turnover": None,
                                "gross_pnl": None,
                                "brokerage": None,
                                "taxes": None,
                                "net_pnl": None,
                                "pnl_pct": None,
                                "duration": f"{duration_days}d (Running)" if duration_days > 0 else "Running",
                                "duration_days": duration_days,
                                "mae_pct": round(mae_pct, 2),
                                "mfe_pct": round(mfe_pct, 2),
                                "weekday": weekday_str,
                                "is_open": True
                            })
                        else:
                            eff_entry = entry_price * (1.0 + slippage_pct / 100.0)
                            eff_exit = exit_price * (1.0 - slippage_pct / 100.0)
                            turnover = (eff_entry + eff_exit) * qty
                            gross_pnl = (eff_exit - eff_entry) * qty
                            brok = (brokerage_per_order * 2.0) if include_brokerage else 0.0
                            tax = (turnover * 0.001 + (brok * 0.18)) if include_taxes else 0.0
                            net_pnl = gross_pnl - brok - tax
                            pnl_pct = ((eff_exit - eff_entry) / eff_entry) * 100.0

                            raw_trades.append({
                                "trade_id": trade_id,
                                "symbol": symbol,
                                "type": "Long",
                                "trigger_date": entry_trigger_dt,
                                "entry_date": entry_dt,
                                "entry_price": round(entry_price, 2),
                                "exit_date": dates[i],
                                "exit_price": round(exit_price, 2),
                                "exit_reason": exit_reason,
                                "qty": qty,
                                "turnover": round(turnover, 2),
                                "gross_pnl": round(gross_pnl, 2),
                                "brokerage": round(brok, 2),
                                "taxes": round(tax, 2),
                                "net_pnl": round(net_pnl, 2),
                                "pnl_pct": round(pnl_pct, 2),
                                "duration": f"{duration_days}d" if duration_days > 0 else "Same Day",
                                "duration_days": duration_days,
                                "mae_pct": round(mae_pct, 2),
                                "mfe_pct": round(mfe_pct, 2),
                                "weekday": weekday_str,
                                "is_open": False
                            })
                        trade_id += 1
                        in_trade = False

            # After candle loop, if trade is still active, append as End of Data
            if in_trade and n > 0:
                last_i = n - 1
                exit_price = float(closes[last_i])
                trade_lows = lows[entry_idx : last_i + 1]
                trade_highs = highs[entry_idx : last_i + 1]
                min_p = float(np.min(trade_lows)) if len(trade_lows) > 0 else entry_price
                max_p = float(np.max(trade_highs)) if len(trade_highs) > 0 else entry_price
                mae_pct = max(0.0, ((entry_price - min_p) / entry_price) * 100.0) if entry_price > 0 else 0.0
                mfe_pct = max(0.0, ((max_p - entry_price) / entry_price) * 100.0) if entry_price > 0 else 0.0

                try:
                    d_in = datetime.strptime(entry_dt[:10], '%Y-%m-%d')
                    d_out = datetime.strptime(dates[last_i][:10], '%Y-%m-%d')
                    duration_days = (d_out - d_in).days
                    weekday_str = d_in.strftime('%a')
                except Exception:
                    duration_days = last_i - entry_idx
                    weekday_str = "Mon"

                raw_trades.append({
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "type": "Long",
                    "trigger_date": entry_trigger_dt,
                    "entry_date": entry_dt,
                    "entry_price": round(entry_price, 2),
                    "exit_date": dates[last_i],
                    "exit_price": round(exit_price, 2),
                    "exit_reason": "End of Data",
                    "qty": qty,
                    "turnover": None,
                    "gross_pnl": None,
                    "brokerage": None,
                    "taxes": None,
                    "net_pnl": None,
                    "pnl_pct": None,
                    "duration": f"{duration_days}d (Running)" if duration_days > 0 else "Running",
                    "duration_days": duration_days,
                    "mae_pct": round(mae_pct, 2),
                    "mfe_pct": round(mfe_pct, 2),
                    "weekday": weekday_str,
                    "is_open": True
                })
                trade_id += 1
                in_trade = False

        except Exception as e:
            error_count += 1
            last_error = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error backtesting symbol {symbol}: {e}")

    duration = round(time.time() - start_time, 2)
    logger.info(f"Backtest completed in {duration}s. Generated {len(raw_trades)} trades.")

    if len(raw_trades) == 0 and error_count == len(symbols) and error_count > 0:
        return {"status": "error", "message": f"Execution error in backtest(df): {last_error}"}

    analytics = compute_backtest_analytics(
        raw_trades,
        slippage_pct=slippage_pct,
        include_brokerage=include_brokerage,
        include_taxes=include_taxes,
        brokerage_per_order=brokerage_per_order,
        capital_per_trade=capital_per_trade
    )

    return {
        "status": "success",
        "timeframe": timeframe,
        "total_trades": len(analytics["trades"]),
        "duration_seconds": duration,
        "trades": analytics["trades"],
        "overall_report": analytics["overall_report"],
        "year_wise_returns": analytics["year_wise_returns"],
        "drawdown_chart": analytics["drawdown_chart"],
        "summary": analytics["summary"]
    }


# =====================================================================
# Flask Application Definition & REST APIs
# =====================================================================

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def api_status():
    df = load_database()
    parquet_symbols = get_available_parquet_symbols()
    
    latest_date = None
    oldest_date = None
    total_sessions = 0
    
    if not df.empty:
        dates = sorted(df['Date'].unique().tolist(), reverse=True)
        latest_date = dates[0] if dates else None
        oldest_date = dates[-1] if dates else None
        total_sessions = len(dates)
    
    return jsonify({
        "status": "ok",
        "has_data": len(parquet_symbols) > 0 or not df.empty,
        "total_records": len(df),
        "total_symbols": max(len(parquet_symbols), len(df['Symbol'].unique()) if not df.empty else 0),
        "parquet_symbols_count": len(parquet_symbols),
        "parquet_dir": ZERODHA_MINUTE_DIR,
        "latest_date": latest_date,
        "oldest_date": oldest_date,
        "total_sessions": total_sessions
    })

@app.route('/api/dates', methods=['GET'])
def api_dates():
    df = load_database()
    if not df.empty:
        dates = sorted(df['Date'].unique().tolist(), reverse=True)
        return jsonify({"dates": dates})
    
    # Fallback to duckdb dates from sample ticker
    try:
        con = get_duckdb_connection()
        p = get_ticker_parquet_path('RELIANCE')
        if p:
            dates = con.execute("SELECT DISTINCT CAST(date AS DATE)::VARCHAR as d FROM read_parquet(?) ORDER BY d DESC", [p.replace('\\', '/')]).fetchdf()['d'].tolist()
            return jsonify({"dates": dates})
    except Exception:
        pass
        
    return jsonify({"dates": []})

@app.route('/api/session-summary', methods=['GET'])
def api_session_summary():
    date_str = request.args.get('date')
    df = load_database()
    if df.empty:
        return jsonify({"status": "error", "message": "Database is empty"}), 400

    if not date_str:
        dates = sorted(df['Date'].unique().tolist(), reverse=True)
        if not dates:
            return jsonify({"status": "error", "message": "No dates available"}), 400
        date_str = dates[0]

    df_date = df[df['Date'] == date_str].copy()
    if df_date.empty:
        return jsonify({"status": "error", "message": f"No data for date {date_str}"}), 404

    df_date['Prev_Close'] = pd.to_numeric(df_date['Prev_Close'], errors='coerce').fillna(0)
    df_date['Close'] = pd.to_numeric(df_date['Close'], errors='coerce').fillna(0)
    df_date['Volume'] = pd.to_numeric(df_date['Volume'], errors='coerce').fillna(0)

    df_valid = df_date[df_date['Prev_Close'] > 0].copy()
    df_valid['Pct_Change'] = ((df_valid['Close'] - df_valid['Prev_Close']) / df_valid['Prev_Close'] * 100).round(2)

    top_gainers = df_valid.sort_values(by='Pct_Change', ascending=False).head(10)[['Symbol', 'Close', 'Pct_Change', 'Volume']].to_dict('records')
    top_losers = df_valid.sort_values(by='Pct_Change', ascending=True).head(10)[['Symbol', 'Close', 'Pct_Change', 'Volume']].to_dict('records')
    top_volume = df_date.sort_values(by='Volume', ascending=False).head(10)[['Symbol', 'Close', 'Volume']].to_dict('records')

    # Market breadth stats
    advances = int((df_valid['Pct_Change'] > 0).sum())
    declines = int((df_valid['Pct_Change'] < 0).sum())
    unchanged = int((df_valid['Pct_Change'] == 0).sum())

    return jsonify({
        "status": "ok",
        "date": date_str,
        "total_stocks": len(df_date),
        "breadth": {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged
        },
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "top_volume": top_volume
    })

@app.route('/api/symbols', methods=['GET'])
def api_symbols():
    segment = request.args.get('segment', 'all')
    if segment == 'nifty50':
        symbols = fetch_nifty50_symbols()
    elif segment == 'nifty500':
        symbols = fetch_nifty500_symbols()
    elif segment == 'fno':
        symbols = fetch_fno_symbols()
    else:
        symbols = get_available_parquet_symbols()
        if not symbols:
            df = load_database()
            symbols = sorted(df['Symbol'].dropna().unique().tolist()) if not df.empty else []

    return jsonify({"symbols": symbols, "count": len(symbols)})

@app.route('/api/chart-data', methods=['GET'])
def api_chart_data():
    symbol = request.args.get('symbol', '').upper().strip()
    timeframe = request.args.get('timeframe', '1d').lower().strip()
    
    if not symbol:
        return jsonify({"status": "error", "message": "Symbol parameter is required"}), 400

    # Query via DuckDB from Zerodha minute Parquet
    df_symbol = get_ticker_data_duckdb(symbol, timeframe=timeframe, auto_adjust=True)

    df_db = load_database()
    if df_symbol.empty:
        # Fallback to consolidated DB if parquet doesn't exist
        if not df_db.empty:
            df_match = df_db[df_db['Symbol'] == symbol]
            if not df_match.empty:
                df_symbol = df_match.copy().sort_values(by='Date', ascending=True)
                df_symbol = adjust_parquet_splits(df_symbol, symbol)
    elif timeframe in ['1d', 'daily', 'day'] and not df_db.empty:
        # Supplement any newly synced dates from consolidated DB
        df_match = df_db[df_db['Symbol'] == symbol]
        if not df_match.empty:
            parquet_dates = set(df_symbol['Date'].unique())
            missing_in_parquet = df_match[~df_match['Date'].isin(parquet_dates)]
            if not missing_in_parquet.empty:
                missing_clean = pd.DataFrame({
                    'Date': missing_in_parquet['Date'].astype(str),
                    'Open': pd.to_numeric(missing_in_parquet['Open'], errors='coerce').fillna(0).round(2),
                    'High': pd.to_numeric(missing_in_parquet['High'], errors='coerce').fillna(0).round(2),
                    'Low': pd.to_numeric(missing_in_parquet['Low'], errors='coerce').fillna(0).round(2),
                    'Close': pd.to_numeric(missing_in_parquet['Close'], errors='coerce').fillna(0).round(2),
                    'Volume': pd.to_numeric(missing_in_parquet['Volume'], errors='coerce').fillna(0).round(0).astype('int64', errors='ignore'),
                    'Prev_Close': pd.to_numeric(missing_in_parquet['Prev_Close'], errors='coerce').fillna(0).round(2),
                    'Symbol': symbol
                })
                df_symbol = pd.concat([df_symbol, missing_clean], ignore_index=True).sort_values(by='Date', ascending=True)

    # Always ensure the full dataset is corporate action adjusted
    df_symbol = adjust_parquet_splits(df_symbol, symbol)

    if df_symbol.empty:
        return jsonify({"status": "error", "message": f"No data found for symbol '{symbol}'"}), 404

    splits_dict = get_splits_for_stock(symbol, fetch_online=False)

    latest_row = df_symbol.iloc[-1]
    prev_close = float(latest_row.get('Prev_Close', 0.0))
    close = float(latest_row.get('Close', 0.0))
    pct_change = round(((close - prev_close) / prev_close * 100), 2) if prev_close > 0 else 0.0

    return jsonify({
        "status": "ok",
        "symbol": symbol,
        "timeframe": timeframe,
        "dates": df_symbol['Date'].astype(str).tolist(),
        "open": [round(float(x), 2) for x in df_symbol['Open']],
        "high": [round(float(x), 2) for x in df_symbol['High']],
        "low": [round(float(x), 2) for x in df_symbol['Low']],
        "close": [round(float(x), 2) for x in df_symbol['Close']],
        "volume": [int(x) for x in df_symbol['Volume']],
        "prev_close": [round(float(x), 2) for x in df_symbol['Prev_Close']],
        "splits": splits_dict,
        "latest": {
            "date": str(latest_row['Date']),
            "close": close,
            "prev_close": prev_close,
            "pct_change": pct_change,
            "volume": int(latest_row.get('Volume', 0)),
            "high_period": round(float(df_symbol['High'].max()), 2),
            "low_period": round(float(df_symbol['Low'].min()), 2),
            "total_bars": len(df_symbol)
        }
    })

@app.route('/api/strategies', methods=['GET'])
def api_get_strategies():
    strategies = load_strategies_from_file()
    return jsonify({"strategies": strategies})

@app.route('/api/strategies', methods=['POST'])
def api_save_strategy():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    code = data.get('code', '').strip()
    if not name or not code:
        return jsonify({"status": "error", "message": "Strategy name and code are required"}), 400

    if save_strategy(name, code):
        return jsonify({"status": "ok", "message": f"Strategy '{name}' saved successfully"})
    return jsonify({"status": "error", "message": "Failed to save strategy"}), 500

@app.route('/api/strategies/<path:name>', methods=['DELETE'])
@app.route('/api/strategies', methods=['DELETE'])
def api_delete_strategy(name=None):
    if not name:
        data = request.get_json(silent=True) or {}
        name = data.get('name') or request.args.get('name')
    if not name:
        return jsonify({"status": "error", "message": "Strategy name is required"}), 400
    if delete_strategy(name):
        return jsonify({"status": "ok", "message": f"Strategy '{name}' deleted"})
    return jsonify({"status": "error", "message": f"Strategy '{name}' not found"}), 404

@app.route('/api/screen', methods=['POST'])
def api_screen():
    data = request.get_json() or {}
    code_str = data.get('code', '')
    segment = data.get('segment', 'nifty50')
    timeframe = data.get('timeframe', '1d')
    watchlist = data.get('watchlist', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    min_market_cap_cr = float(data.get('min_market_cap_cr', 2000.0) or 0.0)

    if not code_str:
        return jsonify({"status": "error", "message": "Screening Python code is required"}), 400

    result = run_screener_logic(code_str, segment, timeframe=timeframe, watchlist_symbols=watchlist, start_date=start_date, end_date=end_date, min_market_cap_cr=min_market_cap_cr)
    return jsonify(result)

@app.route('/api/backtest-strategies', methods=['GET'])
def api_get_backtest_strategies():
    strategies = load_backtest_strategies_from_file()
    return jsonify({"strategies": strategies})

@app.route('/api/backtest-strategies', methods=['POST'])
def api_save_backtest_strategy():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    code = data.get('code', '').strip()
    if not name or not code:
        return jsonify({"status": "error", "message": "Backtest strategy name and code are required"}), 400

    if save_backtest_strategy(name, code):
        return jsonify({"status": "ok", "message": f"Backtest strategy '{name}' saved successfully"})
    return jsonify({"status": "error", "message": "Failed to save backtest strategy"}), 500

@app.route('/api/backtest-strategies/<path:name>', methods=['DELETE'])
@app.route('/api/backtest-strategies', methods=['DELETE'])
def api_delete_backtest_strategy(name=None):
    if not name:
        data = request.get_json(silent=True) or {}
        name = data.get('name') or request.args.get('name')
    if not name:
        return jsonify({"status": "error", "message": "Backtest strategy name is required"}), 400
    if delete_backtest_strategy(name):
        return jsonify({"status": "ok", "message": f"Backtest strategy '{name}' deleted"})
    return jsonify({"status": "error", "message": f"Backtest strategy '{name}' not found"}), 404

@app.route('/api/backtest', methods=['POST'])
def api_backtest():
    data = request.get_json() or {}
    code_str = data.get('code', '')
    segment = data.get('segment', 'nifty50')
    timeframe = data.get('timeframe', '1d')
    watchlist = data.get('watchlist', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    capital = float(data.get('capital_per_trade', 100000.0))
    slippage = float(data.get('slippage_pct', 0.5))
    inc_brokerage = bool(data.get('include_brokerage', True))
    inc_taxes = bool(data.get('include_taxes', True))
    brokerage = float(data.get('brokerage_per_order', 20.0))
    min_market_cap_cr = float(data.get('min_market_cap_cr', 2000.0) or 0.0)

    if not code_str:
        return jsonify({"status": "error", "message": "Backtest Python code is required"}), 400

    result = run_backtest_simulation(
        code_str,
        segment=segment,
        timeframe=timeframe,
        watchlist_symbols=watchlist,
        start_date=start_date,
        end_date=end_date,
        capital_per_trade=capital,
        slippage_pct=slippage,
        include_brokerage=inc_brokerage,
        include_taxes=inc_taxes,
        brokerage_per_order=brokerage,
        min_market_cap_cr=min_market_cap_cr
    )
    return jsonify(result)

@app.route('/api/backtest/recalculate', methods=['POST'])
def api_backtest_recalculate():
    data = request.get_json() or {}
    trades = data.get('trades', [])
    slippage = float(data.get('slippage_pct', 0.5))
    inc_brokerage = bool(data.get('include_brokerage', True))
    inc_taxes = bool(data.get('include_taxes', True))
    brokerage = float(data.get('brokerage_per_order', 20.0))
    capital = float(data.get('capital_per_trade', 100000.0))
    weekday_filter = set(data.get('weekdays', [])) if data.get('weekdays') else None
    month_filter = set(data.get('months', [])) if data.get('months') is not None else None

    analytics = compute_backtest_analytics(
        trades,
        slippage_pct=slippage,
        include_brokerage=inc_brokerage,
        include_taxes=inc_taxes,
        brokerage_per_order=brokerage,
        weekday_filter=weekday_filter,
        capital_per_trade=capital,
        month_filter=month_filter
    )
    return jsonify({"status": "success", **analytics})

# --- Zerodha Parquet & Data Manager APIs ---

@app.route('/api/zerodha/status', methods=['GET'])
def api_zerodha_status():
    exists = os.path.exists(ZERODHA_MINUTE_DIR)
    symbols = get_available_parquet_symbols()
    splits_cache = load_splits_cache()
    
    date_info = {}
    if exists and symbols:
        try:
            con = get_duckdb_connection()
            ref_path = get_ticker_parquet_path(symbols[0])
            stats = con.execute("SELECT MIN(date)::VARCHAR, MAX(date)::VARCHAR, COUNT(1) FROM read_parquet(?)", [ref_path.replace('\\', '/')]).fetchone()
            date_info = {
                "sample_symbol": symbols[0],
                "min_datetime": stats[0],
                "max_datetime": stats[1],
                "sample_bars": stats[2]
            }
        except Exception as e:
            logger.error(f"Error checking Zerodha reference stats: {e}")

    return jsonify({
        "status": "ok",
        "exists": exists,
        "directory": ZERODHA_MINUTE_DIR,
        "total_tickers": len(symbols),
        "corporate_actions_tracked": len(splits_cache),
        "duckdb_version": duckdb.__version__,
        "date_info": date_info
    })

@app.route('/api/zerodha/sync-splits', methods=['POST'])
def api_zerodha_sync_splits():
    """
    Refreshes corporate action splits cache from Yahoo Finance for constituents,
    and invalidates affected daily cache files.
    """
    symbols = fetch_nifty50_symbols()
    splits_cache = load_splits_cache()
    updated = 0
    affected_syms = []
    for sym in symbols[:25]:
        try:
            old_sp = splits_cache.get(sym, {})
            sp = get_splits_for_stock(sym, fetch_online=True)
            if sp != old_sp:
                updated += 1
                affected_syms.append(sym)
                # Invalidate daily cache file
                daily_p = os.path.join(ADJUSTED_DAILY_DIR, f"{sym}.parquet")
                if os.path.exists(daily_p):
                    try:
                        os.remove(daily_p)
                    except Exception:
                        pass
        except Exception:
            pass
            
    # Rebuild any invalidated affected stocks
    if affected_syms:
        try:
            from build_daily_cache import build_daily_cache_batch
            build_daily_cache_batch(affected_syms, force=True)
        except Exception:
            pass

    return jsonify({
        "status": "ok",
        "message": f"Refreshed corporate actions splits. Tracked stocks: {len(load_splits_cache())}",
        "total_tracked": len(load_splits_cache())
    })

# --- Pre-Adjusted Daily Parquet Cache REST API Endpoints ---

DAILY_CACHE_SYNC_STATUS = {
    "is_running": False,
    "progress": 0,
    "current": 0,
    "total": 0,
    "symbol": "",
    "status": "idle",
    "message": "",
    "stats": {}
}

@app.route('/api/daily-cache/status', methods=['GET'])
def api_get_daily_cache_status():
    from build_daily_cache import get_daily_cache_status
    cache_info = get_daily_cache_status()
    return jsonify({
        "status": "ok",
        "cache": cache_info,
        "sync_job": DAILY_CACHE_SYNC_STATUS
    })

@app.route('/api/daily-cache/build', methods=['POST'])
def api_build_daily_cache():
    import threading
    data = request.get_json() or {}
    segment = data.get('segment', 'nifty50')
    symbols = data.get('symbols', [])
    force = bool(data.get('force', False))

    if DAILY_CACHE_SYNC_STATUS["is_running"]:
        return jsonify({
            "status": "busy",
            "message": "A daily cache build job is already in progress.",
            "sync_job": DAILY_CACHE_SYNC_STATUS
        }), 409

    from build_daily_cache import get_symbols_for_segment, build_daily_cache_batch
    if not symbols:
        symbols = get_symbols_for_segment(segment)

    if not symbols:
        return jsonify({"status": "error", "message": f"No symbols found for segment '{segment}'"}), 400

    def run_worker():
        DAILY_CACHE_SYNC_STATUS["is_running"] = True
        DAILY_CACHE_SYNC_STATUS["progress"] = 0
        DAILY_CACHE_SYNC_STATUS["current"] = 0
        DAILY_CACHE_SYNC_STATUS["total"] = len(symbols)
        DAILY_CACHE_SYNC_STATUS["status"] = "running"
        DAILY_CACHE_SYNC_STATUS["message"] = f"Building daily cache for {len(symbols)} stocks..."

        def cb(curr, tot, sym, st):
            DAILY_CACHE_SYNC_STATUS["current"] = curr
            DAILY_CACHE_SYNC_STATUS["total"] = tot
            DAILY_CACHE_SYNC_STATUS["symbol"] = sym
            DAILY_CACHE_SYNC_STATUS["progress"] = round((curr / tot) * 100, 1) if tot > 0 else 100
            DAILY_CACHE_SYNC_STATUS["message"] = f"[{curr}/{tot}] {sym} ({st})"

        try:
            stats = build_daily_cache_batch(symbols, force=force, progress_callback=cb)
            DAILY_CACHE_SYNC_STATUS["status"] = "complete"
            DAILY_CACHE_SYNC_STATUS["stats"] = stats
            DAILY_CACHE_SYNC_STATUS["message"] = f"Daily cache build complete: {stats.get('created', 0) + stats.get('updated', 0)} built, {stats.get('cached', 0)} cached."
        except Exception as e:
            logger.error(f"Daily cache worker error: {e}")
            DAILY_CACHE_SYNC_STATUS["status"] = "error"
            DAILY_CACHE_SYNC_STATUS["message"] = f"Build failed: {str(e)}"
        finally:
            DAILY_CACHE_SYNC_STATUS["is_running"] = False

    t = threading.Thread(target=run_worker, daemon=True)
    t.start()

    return jsonify({
        "status": "ok",
        "message": f"Started pre-adjusted daily cache build for {len(symbols)} stocks.",
        "sync_job": DAILY_CACHE_SYNC_STATUS
    })

# --- Fundamentals REST API Endpoints ---

@app.route('/api/fundamentals/<symbol>', methods=['GET'])
def api_get_stock_fundamentals_route(symbol):
    fetch_online = request.args.get('fetch_online', 'true').lower() in ['true', '1', 'yes']
    data = get_stock_statement(symbol, fetch_online=fetch_online)
    if not data or not data.get('ratios'):
        ratios = get_stock_fundamentals(symbol, fetch_online=fetch_online)
        if ratios:
            data = {
                "symbol": symbol.upper(),
                "ratios": ratios,
                "quarterly_pnl": {},
                "yearly_pnl": {},
                "yearly_balance_sheet": {},
                "quarterly_balance_sheet": {},
                "yearly_cash_flow": {}
            }
    if data:
        return jsonify({"status": "ok", "data": data})
    return jsonify({"status": "error", "message": f"Could not find fundamentals for {symbol}"}), 404

@app.route('/api/fundamentals/summary', methods=['GET'])
def api_get_fundamentals_summary():
    summary = load_fundamentals_cache()
    return jsonify({"status": "ok", "data": summary, "count": len(summary)})

@app.route('/api/fundamentals/status', methods=['GET'])
def api_get_fundamentals_status():
    summary = load_fundamentals_cache()
    latest_ts = None
    for r in summary.values():
        ts = r.get('lastUpdated')
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
    return jsonify({
        "status": "ok",
        "total_tracked": len(summary),
        "last_sync": latest_ts,
        "sync_job": FUNDAMENTALS_SYNC_STATUS
    })

@app.route('/api/fundamentals/sync', methods=['POST'])
def api_sync_fundamentals():
    import threading
    data = request.get_json() or {}
    segment = data.get('segment', 'nifty50')
    symbols = data.get('symbols', [])
    force = bool(data.get('force', False))

    if FUNDAMENTALS_SYNC_STATUS["is_running"]:
        return jsonify({
            "status": "busy",
            "message": "A fundamentals sync job is already in progress.",
            "sync_job": FUNDAMENTALS_SYNC_STATUS
        }), 409

    if not symbols:
        from download_fundamentals import get_symbols_for_segment
        symbols = get_symbols_for_segment(segment)

    if not symbols:
        return jsonify({"status": "error", "message": f"No symbols found for segment '{segment}'"}), 400

    def run_sync():
        global FUNDAMENTALS_SYNC_STATUS
        FUNDAMENTALS_SYNC_STATUS["is_running"] = True
        FUNDAMENTALS_SYNC_STATUS["total"] = len(symbols)
        FUNDAMENTALS_SYNC_STATUS["current"] = 0
        FUNDAMENTALS_SYNC_STATUS["status"] = "running"
        try:
            from download_fundamentals import download_fundamentals_batch
            def on_progress(cur, tot, sym, stat):
                FUNDAMENTALS_SYNC_STATUS["current"] = cur
                FUNDAMENTALS_SYNC_STATUS["total"] = tot
                FUNDAMENTALS_SYNC_STATUS["current_symbol"] = sym

            download_fundamentals_batch(symbols, force=force, delay=0.35, progress_callback=on_progress)
            load_fundamentals_cache(force_reload=True)
            FUNDAMENTALS_SYNC_STATUS["status"] = "completed"
            FUNDAMENTALS_SYNC_STATUS["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error(f"Error in fundamentals sync thread: {e}")
            FUNDAMENTALS_SYNC_STATUS["status"] = f"error: {str(e)}"
        finally:
            FUNDAMENTALS_SYNC_STATUS["is_running"] = False

    t = threading.Thread(target=run_sync, daemon=True)
    t.start()

    return jsonify({
        "status": "ok",
        "message": f"Started background fundamentals download for {len(symbols)} stocks ({segment}).",
        "total": len(symbols),
        "sync_job": FUNDAMENTALS_SYNC_STATUS
    })

@app.route('/api/sync-data', methods=['POST'])
def api_sync_data():
    data = request.get_json() or {}
    start_str = data.get('start_date')
    end_str = data.get('end_date')

    if not start_str or not end_str:
        return jsonify({"status": "error", "message": "Both start_date and end_date are required"}), 400

    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_str, "%Y-%m-%d")
    except Exception:
        return jsonify({"status": "error", "message": "Invalid date format. Use YYYY-MM-DD"}), 400

    df = load_database()
    existing_dates = set(df['Date'].unique()) if not df.empty else set()

    curr = start_dt
    target_dates = []
    now_date = datetime.now().date()

    while curr <= end_dt:
        if curr.date() <= now_date and curr.weekday() < 5:
            if curr.strftime('%Y-%m-%d') not in existing_dates:
                target_dates.append(curr)
        curr += timedelta(days=1)

    if not target_dates:
        return jsonify({"status": "info", "message": "No missing trading days found in selected range."})

    all_cleaned = []
    for d in target_dates:
        date_url_str = format_date_for_url(d)
        filename = f"sec_bhavdata_full_{date_url_str}.csv"
        filepath = os.path.join(BHAV_DIR, filename)
        raw_data = None

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    raw_data = f.read()
            except Exception:
                pass

        if not raw_data:
            raw_data = download_bhavcopy_from_nse(d)
            if raw_data:
                save_daily_bhav(d, raw_data)

        if raw_data:
            try:
                raw_df = pd.read_csv(io.StringIO(raw_data))
                cleaned = clean_bhavcopy(raw_df)
                if not cleaned.empty:
                    all_cleaned.append(cleaned)
            except Exception as e:
                logger.error(f"Error parsing data for {d.strftime('%Y-%m-%d')}: {e}")

    if all_cleaned:
        concatenated = pd.concat(all_cleaned, ignore_index=True)
        df = update_consolidated_database(concatenated, df)
        return jsonify({
            "status": "ok",
            "message": f"Range sync complete! Added {len(all_cleaned)} trading sessions ({len(concatenated):,} records).",
            "sessions_synced": len(all_cleaned),
            "records_added": len(concatenated)
        })
    return jsonify({"status": "error", "message": "Failed to download any new dates in range."}), 404

@app.route('/api/export-database', methods=['GET'])
def api_export_database():
    if os.path.exists(CONSOLIDATED_FILE) and os.path.getsize(CONSOLIDATED_FILE) > 0:
        filename = f"nse_consolidated_database_{datetime.now().strftime('%Y%m%d')}.csv"
        return send_file(CONSOLIDATED_FILE, as_attachment=True, download_name=filename, mimetype='text/csv')
    return jsonify({"status": "error", "message": "Database file not found"}), 404

def generate_backtest_pdf(report_data):
    if not HAS_REPORTLAB:
        raise RuntimeError("ReportLab is not installed. Run 'pip install reportlab' to enable PDF export.")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.HexColor('#475569'),
        spaceAfter=12
    )
    section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=10,
        spaceAfter=6
    )
    
    elements = []
    
    # 1. Title & Metadata
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
    elements.append(Spacer(1, 4))
    
    # 2. Overall Report (4-column institutional layout)
    rep = report_data.get('overall_report', {})
    elements.append(Paragraph("Overall Performance Summary", section_title))
    
    ov_profit = rep.get('overall_profit', 0.0)
    profit_color = colors.HexColor('#16a34a') if ov_profit >= 0 else colors.HexColor('#dc2626')
    
    col1 = [
        ["Returns & Win Rates", "Value"],
        ["Overall Profit / Loss", f"Rs {ov_profit:,.2f}"],
        ["CAGR / Ann. Return", f"{rep.get('cagr_pct', 0.0):.2f}%"],
        ["Closed Trades", str(rep.get('no_of_trades', 0))],
        ["Running Trades (EOD)", str(rep.get('open_trades', 0))],
        ["Win % / Loss %", f"{rep.get('win_pct', 0.0):.1f}% / {rep.get('loss_pct', 0.0):.1f}%"],
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
        ["Reward to Risk", f"{rep.get('reward_to_risk_ratio', 0.0):.2f}"],
        ["Expectancy Ratio", f"{rep.get('expectancy_ratio', 0.0):.2f}"],
        ["Return over Max DD", f"{rep.get('return_over_max_dd', 0.0):.2f}"],
        ["Max Drawdown", f"Rs {rep.get('max_drawdown', 0.0):,.2f}"],
    ]
    col3 = [
        ["Capital & Exposure", "Value"],
        ["Peak Capital Deployed", f"Rs {rep.get('peak_capital_deployed', 0.0):,.0f}"],
        ["Max Concurrent Pos", str(rep.get('max_concurrent_positions', 1))],
        ["Capital Utilization", f"{rep.get('capital_utilization_pct', 0.0):.1f}%"],
        ["Top 5 Concentration", str(rep.get('symbol_concentration_str', '-'))],
        ["Max Trades in DD", str(rep.get('max_trades_in_drawdown', 0))],
        ["Max Single Profit", f"Rs {rep.get('max_profit_single', 0.0):,.2f}"],
        ["Max Single Loss", f"Rs {rep.get('max_loss_single', 0.0):,.2f}"],
        ["Duration of Max DD", str(rep.get('duration_of_max_drawdown', '-'))[:15]],
    ]
    col4 = [
        ["Trade Diagnostics", "Value"],
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
        t = Table(data_matrix, colWidths=[118, 77])
        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#93c5fd')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
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
    
    summary_table = Table([[t1, t2, t3, t4]], colWidths=[195, 195, 195, 195])
    summary_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 10))
    
    # 3. Year-wise Returns Matrix Table
    elements.append(Paragraph("Year-wise & Month-wise Returns (Rs)", section_title))
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    headers = ['Year'] + months + ['Total', 'Max DD', 'Days for MDD', 'CAGR']
    
    rows_data = [headers]
    yw_rows = report_data.get('year_wise_returns', [])
    
    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
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
        
    col_w = [38] + [42]*12 + [54, 52, 72, 44]
    matrix_table = Table(rows_data, colWidths=col_w)
    matrix_table.setStyle(TableStyle(style_commands))
    elements.append(matrix_table)
    
    # 4. Summary Costs Footer
    summary = report_data.get('summary', {})
    tot_brok = summary.get('total_brokerage', 0.0)
    tot_tax = summary.get('total_taxes', 0.0)
    elements.append(Spacer(1, 8))
    footer_text = f"Total Estimated Brokerage: <b>Rs {tot_brok:,.2f}</b> | Total Taxes & Regulatory Charges: <b>Rs {tot_tax:,.2f}</b>"
    elements.append(Paragraph(footer_text, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#64748b'))))

    # 5. Drawdown Section & Chart
    dd_data = report_data.get('drawdown_chart', {})
    dd_dates = dd_data.get('dates', [])
    dd_vals = dd_data.get('drawdowns', [])

    if dd_dates and dd_vals:
        elements.append(PageBreak())
        elements.append(Paragraph("<b>Underwater Drawdown Analysis</b>", section_title))

        # Summary Box for Drawdown
        mdd_val = rep.get('max_drawdown', 0.0)
        mdd_dur = rep.get('duration_of_max_drawdown', '-')
        trades_in_dd = rep.get('max_trades_in_drawdown', 0)
        ret_mdd = rep.get('return_over_max_dd', 0.0)

        dd_summary_matrix = [
            ["Max Drawdown (Rs)", "Duration of Max Drawdown", "Max Trades in Drawdown", "Return / Max DD"],
            [f"Rs {mdd_val:,.2f}", str(mdd_dur), str(trades_in_dd), f"{ret_mdd:.2f}"]
        ]
        dd_summary_table = Table(dd_summary_matrix, colWidths=[195, 235, 175, 175])
        dd_summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TEXTCOLOR', (0, 1), (0, 1), colors.HexColor('#dc2626')),
        ]))
        elements.append(dd_summary_table)
        elements.append(Spacer(1, 12))

        # Render Drawdown Chart using Matplotlib
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates

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
                ax.plot(parsed_dates, valid_vals, color='#ef4444', linewidth=1.5, label='Underwater Drawdown (₹)')
                ax.fill_between(parsed_dates, 0, valid_vals, color='#ef4444', alpha=0.18)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
                fig.autofmt_xdate(rotation=20)
                ax.grid(True, linestyle='--', alpha=0.5, color='#cbd5e1')
                ax.axhline(0, color='#64748b', linestyle='-', linewidth=0.8)
                ax.set_ylabel('Drawdown (₹)', fontsize=9, fontweight='bold', color='#334155')
                ax.set_title('Drawdown Timeline Over Backtest Horizon', fontsize=11, fontweight='bold', color='#0f172a', pad=10)
                ax.legend(loc='lower left', framealpha=0.9, fontsize=8)

                plt.tight_layout()
                chart_buf = io.BytesIO()
                fig.savefig(chart_buf, format='png', bbox_inches='tight')
                plt.close(fig)
                chart_buf.seek(0)

                elements.append(RLImage(chart_buf, width=780, height=270))
        except Exception as e:
            logger.error(f"Failed to plot drawdown chart for PDF: {e}")

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

@app.route('/api/export-results', methods=['POST'])
def api_export_results():
    data = request.get_json() or {}
    results = data.get('results', [])
    export_format = data.get('format', 'excel')
    strategy_name = data.get('strategy_name') or data.get('name') or ''

    if not results:
        return jsonify({"status": "error", "message": "No results to export"}), 400

    # Detect if this is a Backtest Trades export or Screener Results export
    is_backtest_export = False
    first_item = results[0] if results else {}
    if any(k in first_item for k in ['Trade #', 'trade_id', 'Entry Date', 'entry_date', 'Exit Price', 'exit_price', 'Quantity', 'Qty']):
        is_backtest_export = True

    if is_backtest_export:
        df_export = pd.DataFrame(results)
        sheet_title = 'Backtest Trades'
        if strategy_name:
            filename_prefix = re.sub(r'[\\/*?:"<>|]', '_', strategy_name).strip()
        else:
            filename_prefix = 'backtest_trades'

        # STRICT GUARANTEE: For any 'End of Data' / running rows, NEVER calculate or output P/L, turnover, or costs
        is_eod_mask = pd.Series(False, index=df_export.index)
        for col in df_export.columns:
            col_l = col.lower()
            if 'exit' in col_l or 'reason' in col_l:
                is_eod_mask = is_eod_mask | df_export[col].astype(str).str.contains(r'end.*data|running', case=False, na=False)
            elif 'open' in col_l or 'status' in col_l:
                is_eod_mask = is_eod_mask | df_export[col].astype(str).str.contains(r'true|open|running', case=False, na=False)
            elif 'duration' in col_l:
                is_eod_mask = is_eod_mask | df_export[col].astype(str).str.contains(r'running', case=False, na=False)

        for col in df_export.columns:
            col_l = col.lower()
            if 'date' in col_l:
                df_export[col] = df_export[col].apply(lambda v: format_date_dd_mmm_yyyy(v) if v not in [None, '', '-', 'nan', 'None'] else '-')
            elif any(term in col_l for term in ['turnover', 'gross', 'net', 'pnl', 'p&l', 'brokerage', 'tax', 'profit', 'loss']):
                df_export[col] = df_export[col].astype(object)
                df_export.loc[is_eod_mask, col] = '-'
                # Also replace any null / NaN values with '-'
                df_export[col] = df_export[col].apply(lambda v: '-' if v is None or pd.isna(v) or str(v).strip().lower() in ['nan', 'none', ''] else v)
    else:
        unwanted_cols = {
            'avg_volume_20', 'close', 'monthly_r2', 'volume', 'volume_ratio',
            'in_trade', 'stage', 'stop_loss', 'entries', 'signal'
        }
        flat_rows = []
        for item in results:
            row = {
                "Date / Time": format_date_dd_mmm_yyyy(item.get("Date", "")),
                "Symbol": item.get("Symbol", ""),
                "Close Price": item.get("Close", 0.0),
                "Change (%)": item.get("Pct_Change", 0.0)
            }
            custom_dict = item.get("custom_data", {})
            if "R2_Cross_Date" in custom_dict:
                row["R2 Cross Date"] = format_date_dd_mmm_yyyy(custom_dict["R2_Cross_Date"])
            for k, v in custom_dict.items():
                if k != "R2_Cross_Date" and k.lower() not in unwanted_cols:
                    col_name = k.replace('_', ' ')
                    val = v
                    if 'date' in col_name.lower():
                        val = format_date_dd_mmm_yyyy(val)
                    row[col_name] = val
            flat_rows.append(row)

        df_export = pd.DataFrame(flat_rows)
        sheet_title = 'Screener Results'
        if strategy_name:
            filename_prefix = re.sub(r'[\\/*?:"<>|]', '_', strategy_name).strip()
        else:
            filename_prefix = 'screener_results'

    if export_format == 'csv':
        buffer = io.StringIO()
        df_export.to_csv(buffer, index=False)
        mem = io.BytesIO(buffer.getvalue().encode('utf-8'))
        filename = f"{filename_prefix}.csv"
        return send_file(mem, as_attachment=True, download_name=filename, mimetype='text/csv')
    else:
        mem = io.BytesIO()
        with pd.ExcelWriter(mem, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name=sheet_title)
        mem.seek(0)
        filename = f"{filename_prefix}.xlsx"
        return send_file(mem, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/export-backtest-pdf', methods=['POST'])
def api_export_backtest_pdf():
    data = request.get_json() or {}
    if not data:
        return jsonify({"status": "error", "message": "No data provided for PDF export"}), 400

    try:
        pdf_bytes = generate_backtest_pdf(data)
        strategy_name = data.get('strategy_name') or 'Backtest_Report'
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', strategy_name).strip()
        filename = f"{safe_name}_Backtest_Report.pdf"
        
        mem = io.BytesIO(pdf_bytes)
        mem.seek(0)
        return send_file(mem, as_attachment=True, download_name=filename, mimetype='application/pdf')
    except Exception as e:
        logger.error(f"Error generating PDF report: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Failed to generate PDF: {str(e)}"}), 500

@app.route('/api/upload-watchlist', methods=['POST'])
def api_upload_watchlist():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"status": "error", "message": "Empty file name"}), 400

    try:
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            df_up = pd.read_csv(file)
        else:
            df_up = pd.read_excel(file)

        symbol_col = None
        for col in df_up.columns:
            if 'SYMBOL' in str(col).upper() or 'TICKER' in str(col).upper():
                symbol_col = col
                break
        if symbol_col is None:
            symbol_col = df_up.columns[0]

        symbols = df_up[symbol_col].dropna().astype(str).str.strip().str.upper().unique().tolist()
        symbols = [s for s in symbols if s and len(s) < 20]

        return jsonify({
            "status": "ok",
            "symbols": symbols,
            "count": len(symbols),
            "message": f"Successfully parsed {len(symbols)} tickers from {file.filename}"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to parse watchlist file: {e}"}), 500


# --- Server Runner ---

def run_server(port=8000):
    url = f"http://localhost:{port}"
    print("=" * 60)
    print(" ChethanQuant Stock Screener & Backtester is running!")
    print(f" Local URL: {url}")
    print(" Press Ctrl + C to stop the server.")
    print("=" * 60)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except OSError as e:
        if "address already in use" in str(e).lower() or getattr(e, 'winerror', 0) == 10048:
            print(f"[!] Port {port} is busy, trying port {port + 1}...")
            run_server(port + 1)
        else:
            raise e

if __name__ == "__main__":
    run_server()

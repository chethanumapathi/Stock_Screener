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

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Directory Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BHAV_DIR = os.path.join(DATA_DIR, 'bhavcopies')
CONSOLIDATED_FILE = os.path.join(DATA_DIR, 'consolidated_data.csv')
SPLITS_CACHE_FILE = os.path.join(DATA_DIR, 'splits_cache.json')
STRATEGIES_FILE = os.path.join(DATA_DIR, 'strategies.json')
NIFTY50_FILE = os.path.join(DATA_DIR, 'nifty50.csv')
NIFTY500_FILE = os.path.join(DATA_DIR, 'nifty500.csv')
FNO_FILE = os.path.join(DATA_DIR, 'fno.csv')

# Zerodha Historical Minute Parquet Directory
ZERODHA_MINUTE_DIR = r"C:\Zerodha Historical Data\data\minute"

# Ensure local directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BHAV_DIR, exist_ok=True)

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
    parquet_path = get_ticker_parquet_path(symbol)
    if not parquet_path:
        return pd.DataFrame()

    con = get_duckdb_connection()

    # Timeframe SQL generation
    timeframe = timeframe.lower()
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
                    time_bucket(INTERVAL '1 Hour', date) AS date,
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
    df['Symbol'] = symbol

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

def run_screener_logic(code_str, segment, timeframe='1d', watchlist_symbols=None, start_date=None, end_date=None):
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
    }
    try:
        exec(code_str, exec_env)
        if 'screen' not in exec_env or not callable(exec_env['screen']):
            return {"status": "error", "message": "The code must define a callable function named 'screen(df)'"}
        screen_func = exec_env['screen']
    except Exception as e:
        return {"status": "error", "message": f"Compile error: {str(e)}"}

    start_time = time.time()
    logger.info(f"Screening {len(symbols)} stocks on timeframe '{timeframe}' using custom code...")

    historical_results = {}
    total_matches = 0
    error_count = 0
    last_error = ""

    for symbol in symbols:
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
                # Prefer explicit 'entries' (buy trigger event) if returned by strategy; otherwise fallback to 'signal'
                sig = res.get('entries') if ('entries' in res and res['entries'] is not None) else res.get('signal')
                if isinstance(sig, pd.Series):
                    signal_series = sig
                elif isinstance(sig, (np.ndarray, list)):
                    signal_series = pd.Series(sig, index=df_symbol.index[:len(sig)])
                elif isinstance(sig, (bool, np.bool_)):
                    signal_series = pd.Series([False] * len(df_symbol), index=df_symbol.index)
                    if len(df_symbol) > 0:
                        signal_series.iloc[-1] = bool(sig)

                for k, v in res.items():
                    if k not in ['signal', 'entries']:
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
    updated = [s for s in strategies if s['name'].lower() != name.lower()]
    if len(updated) == len(strategies):
        return False
    try:
        with open(STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(updated, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Failed to delete strategy: {e}")
        return False


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

@app.route('/api/strategies/<string:name>', methods=['DELETE'])
def api_delete_strategy(name):
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

    if not code_str:
        return jsonify({"status": "error", "message": "Screening Python code is required"}), 400

    result = run_screener_logic(code_str, segment, timeframe=timeframe, watchlist_symbols=watchlist, start_date=start_date, end_date=end_date)
    return jsonify(result)

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
    Refreshes corporate action splits cache from Yahoo Finance for top constituents.
    """
    symbols = fetch_nifty50_symbols()
    splits_cache = load_splits_cache()
    updated = 0
    for sym in symbols[:15]:
        try:
            sp = get_splits_for_stock(sym, fetch_online=True)
            if sp:
                updated += 1
        except Exception:
            pass
            
    return jsonify({
        "status": "ok",
        "message": f"Refreshed corporate actions splits. Tracked stocks: {len(load_splits_cache())}",
        "total_tracked": len(load_splits_cache())
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

@app.route('/api/export-results', methods=['POST'])
def api_export_results():
    data = request.get_json() or {}
    results = data.get('results', [])
    export_format = data.get('format', 'excel')

    if not results:
        return jsonify({"status": "error", "message": "No results to export"}), 400

    unwanted_cols = {
        'avg_volume_20', 'close', 'monthly_r2', 'volume', 'volume_ratio',
        'in_trade', 'stage', 'stop_loss', 'entries', 'signal'
    }
    flat_rows = []
    for item in results:
        row = {
            "Date / Time": item.get("Date", ""),
            "Symbol": item.get("Symbol", ""),
            "Close Price": item.get("Close", 0.0),
            "Change (%)": item.get("Pct_Change", 0.0)
        }
        custom_dict = item.get("custom_data", {})
        if "R2_Cross_Date" in custom_dict:
            row["R2 Cross Date"] = custom_dict["R2_Cross_Date"]
        for k, v in custom_dict.items():
            if k != "R2_Cross_Date" and k.lower() not in unwanted_cols:
                col_name = k.replace('_', ' ')
                row[col_name] = v
        flat_rows.append(row)

    df_export = pd.DataFrame(flat_rows)

    if export_format == 'csv':
        buffer = io.StringIO()
        df_export.to_csv(buffer, index=False)
        mem = io.BytesIO(buffer.getvalue().encode('utf-8'))
        filename = f"screener_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return send_file(mem, as_attachment=True, download_name=filename, mimetype='text/csv')
    else:
        mem = io.BytesIO()
        with pd.ExcelWriter(mem, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Screener Results')
        mem.seek(0)
        filename = f"screener_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(mem, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

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

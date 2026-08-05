import os
import io
import re
import time
import logging
import json
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BHAV_DIR = os.path.join(DATA_DIR, 'bhavcopies')
CONSOLIDATED_FILE = os.path.join(DATA_DIR, 'consolidated_data.csv')
SPLITS_CACHE_FILE = os.path.join(DATA_DIR, 'splits_cache.json')
STRATEGIES_FILE = os.path.join(DATA_DIR, 'strategies.json')

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

# --- Database & Cache Loading (Streamlit cached) ---

@st.cache_data
def load_database():
    if os.path.exists(CONSOLIDATED_FILE) and os.path.getsize(CONSOLIDATED_FILE) > 0:
        try:
            logger.info("Loading consolidated database into memory...")
            start_time = time.time()
            df = pd.read_csv(CONSOLIDATED_FILE)
            df['Date'] = df['Date'].astype(str)
            df['Symbol'] = df['Symbol'].astype(str)
            df = df.sort_values(by=['Date', 'Symbol'], ascending=[False, True])
            logger.info(f"Loaded {len(df)} records in {time.time() - start_time:.2f} seconds.")
            return df
        except Exception as e:
            logger.error(f"Error loading database into memory: {e}")
    return pd.DataFrame()

# Load splits cache
def load_splits_cache():
    if os.path.exists(SPLITS_CACHE_FILE) and os.path.getsize(SPLITS_CACHE_FILE) > 0:
        try:
            with open(SPLITS_CACHE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading splits cache: {e}")
    return {}

# Helper to save splits cache
def save_splits_cache(cache):
    try:
        with open(SPLITS_CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception as e:
        logger.error(f"Error saving splits cache: {e}")

def get_splits_for_stock(symbol, fetch_online=True):
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

def adjust_for_splits(df_symbol, splits_dict):
    if not splits_dict or df_symbol.empty:
        return df_symbol
        
    df_adj = df_symbol.copy()
    sorted_splits = sorted(splits_dict.items(), key=lambda x: x[0])
    
    for split_date, ratio in sorted_splits:
        if ratio <= 0 or ratio == 1.0:
            continue
        mask = df_adj['Date'] < split_date
        if mask.any():
            for col in ['Open', 'High', 'Low', 'Close', 'Prev_Close', 'Avg_Price']:
                if col in df_adj.columns:
                    df_adj.loc[mask, col] = (df_adj.loc[mask, col] / ratio).round(2)
            if 'Volume' in df_adj.columns:
                df_adj.loc[mask, 'Volume'] = (df_adj.loc[mask, 'Volume'] * ratio).round(0)
                
    return df_adj

@st.cache_data
def get_adjusted_df_for_symbol(db_df, symbol):
    symbol = symbol.upper()
    if db_df.empty:
        return pd.DataFrame()
        
    df_symbol = db_df[db_df['Symbol'] == symbol]
    if df_symbol.empty:
        return pd.DataFrame()
        
    df_symbol = df_symbol.copy()
    if 'Series' in df_symbol.columns:
        df_eq = df_symbol[df_symbol['Series'] == 'EQ']
        if not df_eq.empty:
            df_symbol = df_eq.copy()
            
    df_symbol = df_symbol.drop_duplicates(subset=['Date'])
    df_symbol = df_symbol.sort_values(by='Date', ascending=True)
    
    splits_dict = get_splits_for_stock(symbol, fetch_online=False)
    df_symbol = adjust_for_splits(df_symbol, splits_dict)
    
    return df_symbol

# --- NSE Bhavcopy download helpers ---

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
        
    response = session.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
        if "SYMBOL" in response.text or "SYMBOL" in response.text.upper():
            return response.text
        else:
            logger.warning(f"NSE returned 200 but content did not look like a CSV: {response.text[:200]}")
            return None
    elif response.status_code == 404:
        logger.info(f"Bhavcopy not found (404) for date: {date_obj.strftime('%Y-%m-%d')}")
        return None
    else:
        logger.error(f"Failed download. Status code: {response.status_code}")
        return None

def save_daily_bhav(date_obj, raw_csv_text):
    os.makedirs(BHAV_DIR, exist_ok=True)
    filename = f"sec_bhavdata_full_{format_date_for_url(date_obj)}.csv"
    filepath = os.path.join(BHAV_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(raw_csv_text)
    logger.info(f"Saved daily raw file to {filepath}")
    return filepath

def update_consolidated_database(cleaned_df, current_db_df):
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
        load_database.clear()  # Invalidate Streamlit's data cache
        get_adjusted_df_for_symbol.clear()  # Invalidate stock-adjusted dataframes cache
        logger.info(f"Database updated and saved. Total records: {len(updated_db)}")
    except Exception as e:
        logger.error(f"Failed to write database file: {e}")
        
    return updated_db

# --- Stock lists ---

NIFTY50_FILE = os.path.join(DATA_DIR, 'nifty50.csv')
NIFTY500_FILE = os.path.join(DATA_DIR, 'nifty500.csv')
FNO_FILE = os.path.join(DATA_DIR, 'fno.csv')

def fetch_nifty50_symbols():
    if os.path.exists(NIFTY50_FILE) and os.path.getsize(NIFTY50_FILE) > 0:
        try:
            df = pd.read_csv(NIFTY50_FILE)
            return df['Symbol'].dropna().str.strip().tolist()
        except Exception as e:
            logger.error(f"Error reading local Nifty 50 file: {e}")
            
    try:
        logger.info("Downloading Nifty 50 constituents list...")
        url = "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
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
        logger.info("Downloading Nifty 500 constituents list...")
        url = "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
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
        logger.info("Downloading FnO constituents list...")
        url = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
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

# --- Custom Stock Screener Logic ---

def run_screener_logic(db_df, code_str, segment, watchlist_symbols=None):
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
        if not db_df.empty:
            symbols = db_df['Symbol'].dropna().unique().tolist()
            
    if not db_df.empty:
        db_symbols = set(db_df['Symbol'].unique())
        symbols = [s for s in symbols if s in db_symbols]
        
    results = []
    
    local_env = {}
    try:
        restricted_globals = {
            '__builtins__': __builtins__,
            'pd': pd,
            'np': np,
            'yf': yf,
        }
        exec(code_str, restricted_globals, local_env)
        if 'screen' not in local_env:
            return {"status": "error", "message": "The code must define a function named 'screen(df)'"}
        screen_func = local_env['screen']
    except Exception as e:
        return {"status": "error", "message": f"Compile error: {str(e)}"}
        
    start_time = time.time()
    logger.info(f"Screening {len(symbols)} stocks using custom code...")
    
    historical_results = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(symbols):
        if i % 10 == 0:
            progress_bar.progress((i + 1) / len(symbols))
            status_text.text(f"Screening stock {i+1}/{len(symbols)}: {symbol}...")
            
        df_symbol = get_adjusted_df_for_symbol(db_df, symbol)
        if df_symbol.empty:
            continue
        
        try:
            res = screen_func(df_symbol)
            
            signal_series = None
            custom_series = {}
            
            if isinstance(res, pd.Series):
                signal_series = res.copy()
                if len(signal_series) == len(df_symbol):
                    signal_series.index = df_symbol.index
            elif isinstance(res, dict):
                sig = res.get('signal')
                if isinstance(sig, pd.Series):
                    signal_series = sig.copy()
                    if len(signal_series) == len(df_symbol):
                        signal_series.index = df_symbol.index
                else:
                    signal_series = pd.Series([False] * len(df_symbol), index=df_symbol.index)
                    if len(df_symbol) > 0:
                        signal_series.iloc[-1] = bool(sig)
                
                for k, v in res.items():
                    if k != 'signal':
                        if isinstance(v, pd.Series):
                            v_copy = v.copy()
                            if len(v_copy) == len(df_symbol):
                                v_copy.index = df_symbol.index
                            custom_series[k] = v_copy
                        else:
                            custom_series[k] = pd.Series([v] * len(df_symbol), index=df_symbol.index)
            elif isinstance(res, (bool, np.bool_)):
                signal_series = pd.Series([False] * len(df_symbol), index=df_symbol.index)
                if len(df_symbol) > 0:
                    signal_series.iloc[-1] = bool(res)
            elif isinstance(res, (tuple, list)):
                signal_series = pd.Series([False] * len(df_symbol), index=df_symbol.index)
                if len(df_symbol) > 0:
                    signal_val = bool(res[0]) if len(res) > 0 else False
                    signal_series.iloc[-1] = signal_val
                if len(res) > 1:
                    custom_series["Value"] = pd.Series([res[1]] * len(df_symbol), index=df_symbol.index)
            else:
                continue
                
            match_indices = df_symbol.index[signal_series == True]
            for idx in match_indices:
                row = df_symbol.loc[idx]
                date_str = row['Date']
                
                custom_data = {}
                for k, s_val in custom_series.items():
                    custom_data[k] = s_val.loc[idx]
                    if hasattr(custom_data[k], 'item'):
                        custom_data[k] = custom_data[k].item()
                
                idx_pos = df_symbol.index.get_loc(idx)
                pct_change = 0.0
                if idx_pos > 0:
                    prev_row = df_symbol.iloc[idx_pos - 1]
                    pct_change = ((row['Close'] - prev_row['Close']) / prev_row['Close'] * 100)
                
                res_item = {
                    "Symbol": symbol,
                    "Close": float(row['Close']),
                    "Pct_Change": round(float(pct_change), 2),
                    "Volume": int(row['Volume']),
                    "custom_data": custom_data
                }
                
                if date_str not in historical_results:
                    historical_results[date_str] = []
                historical_results[date_str].append(res_item)
                
        except Exception as e:
            logger.error(f"Error screening symbol {symbol}: {e}")
            
    progress_bar.empty()
    status_text.empty()
    
    total_matches = sum(len(v) for v in historical_results.values())
    logger.info(f"Screening complete. Found {total_matches} matches in {time.time() - start_time:.2f} seconds.")
    return {"status": "success", "historical_results": historical_results}

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
    df['Date'] = pd.to_datetime(df['Date'])
    df['Month'] = df['Date'].dt.to_period('M')

    # --- Step 1: Compute previous month's High, Low, Close for pivot calc ---
    monthly = df.groupby('Month').agg(
        High=('High', 'max'),
        Low=('Low', 'min'),
        Close=('Close', 'last')
    ).reset_index()

    # Shift by 1 so each month uses PREVIOUS month's H/L/C (standard pivot convention)
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

    # --- Step 5: High volume filter (volume > 1.5x its 20-day average) ---
    avg_volume_20 = df['Volume'].rolling(window=20, min_periods=1).mean()
    high_volume = df['Volume'] > (1.5 * avg_volume_20)

    # --- Step 6: Combine conditions ---
    signal = crossed_above_r2 & high_volume

    return {
        "signal": signal,
        "Monthly_R2": df['R2'],
        "Close": df['Close'],
        "Volume": df['Volume'],
        "Avg_Volume_20": avg_volume_20,
        "Volume_Ratio": (df['Volume'] / avg_volume_20).round(2)
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

# --- Streamlit Presentation Layer ---

st.set_page_config(page_title="NSE Stock Screener & Backtester", page_icon="📈", layout="wide")

# Inject premium CSS styles
st.markdown("""
<style>
    /* Import modern typography */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    /* Global font override */
    html, body, [class*="css"], .stApp {
        font-family: 'Outfit', sans-serif !important;
    }
    
    /* Premium glassmorphic background & glow */
    .stApp {
        background-color: #0b0813;
        background-image: radial-gradient(at 0% 0%, rgba(121, 40, 202, 0.08) 0px, transparent 50%),
                          radial-gradient(at 100% 100%, rgba(0, 210, 255, 0.04) 0px, transparent 50%);
    }
    
    /* Metric styling */
    [data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        background: linear-gradient(135deg, #00d2ff, #7928ca);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    /* Glass cards for metrics and forms */
    div[data-testid="metric-container"], .stForm, div[class*="stSelectbox"] {
        background: rgba(24, 20, 44, 0.6) !important;
        border: 1px solid rgba(121, 40, 202, 0.15) !important;
        border-radius: 12px !important;
        padding: 15px !important;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2) !important;
        backdrop-filter: blur(5px) !important;
        -webkit-backdrop-filter: blur(5px) !important;
    }
    
    /* Styled Headers with Gradients */
    h1, h2, h3 {
        font-weight: 700 !important;
        background: linear-gradient(135deg, #ffffff 40%, #a0aec0 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.02em;
    }
    
    /* Buttons customization */
    .stButton>button {
        background: linear-gradient(135deg, #7928ca 0%, #4b0082 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
        box-shadow: 0 4px 15px rgba(121, 40, 202, 0.3) !important;
    }
    .stButton>button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(121, 40, 202, 0.5) !important;
        background: linear-gradient(135deg, #8a3cd8 0%, #5c00a3 100%) !important;
    }
    
    /* Tab custom styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px !important;
        background-color: transparent !important;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: rgba(24, 20, 44, 0.4) !important;
        border: 1px solid rgba(121, 40, 202, 0.08) !important;
        border-radius: 8px !important;
        color: #a0aec0 !important;
        padding: 8px 16px !important;
        transition: all 0.3s ease !important;
    }
    
    .stTabs [aria-selected="true"] {
        background: rgba(121, 40, 202, 0.22) !important;
        border-color: rgba(121, 40, 202, 0.8) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    
    /* File uploader glass */
    div[data-testid="stFileUploader"] {
        border: 1.5px dashed rgba(121, 40, 202, 0.3) !important;
        background-color: rgba(24, 20, 44, 0.4) !important;
        border-radius: 12px !important;
    }
</style>
""", unsafe_allow_html=True)

# Load DB into memory cache
db_df = load_database()

# Sidebar: General Status Info
st.sidebar.title("📈 Stock Screener")
st.sidebar.markdown("---")

if not db_df.empty:
    unique_dates = db_df['Date'].unique().tolist()
    db_dates = sorted(unique_dates, reverse=True)
    st.sidebar.success(f"Database Loaded!")
    st.sidebar.metric("Total Records", f"{len(db_df):,}")
    st.sidebar.metric("Latest Session Date", db_dates[0])
    st.sidebar.metric("Historical Sessions", f"{len(db_dates)}")
else:
    st.sidebar.warning("No data in database. Please download data first!")
    db_dates = []

st.sidebar.markdown("---")
st.sidebar.caption("Data source: NSE India Archives / Bhavcopies")

# Main Title & Subtitle
st.title("📈 NSE India Stock Screener & Backtester")
st.subheader("Explore, analyze, and run custom quantitative screens on historical stock data")

# Set up tabs
tab_dash, tab_screen, tab_charts = st.tabs([
    "📊 Dashboard & Data Manager", 
    "🔍 Custom Quantitative Screener", 
    "📈 Ticker Interactive Chart"
])

# ----------------- TAB 1: DASHBOARD & DATA MANAGER -----------------
with tab_dash:
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.markdown("### 📥 Download & Sync Data")
        st.write("Fetch standard NSE Bhavcopies to build your database.")
        
        down_type = st.radio("Download Mode", ["Single Date", "Date Range"], index=0)
        
        # Prevent downloading future dates
        max_date = datetime.now()
        
        if down_type == "Single Date":
            target_date = st.date_input("Target Date", max_date - timedelta(days=1), max_value=max_date)
            fallback = st.checkbox("Fallback to preceding dates if market was closed", value=True)
            
            if st.button("Download Date", use_container_width=True):
                target_date_dt = datetime.combine(target_date, datetime.min.time())
                
                with st.spinner(f"Attempting to download for {target_date_dt.strftime('%Y-%m-%d')}..."):
                    existing_dates = set(db_df['Date'].unique()) if not db_df.empty else set()
                    
                    current_attempt_date = target_date_dt
                    raw_data = None
                    attempts = 0
                    max_attempts = 7 if fallback else 1
                    
                    while attempts < max_attempts:
                        if current_attempt_date.weekday() < 5:
                            attempt_str = current_attempt_date.strftime('%Y-%m-%d')
                            if attempt_str in existing_dates:
                                st.info(f"Data for {attempt_str} is already available.")
                                break
                            
                            raw_data = download_bhavcopy_from_nse(current_attempt_date)
                            if raw_data:
                                save_daily_bhav(current_attempt_date, raw_data)
                                break
                        current_attempt_date -= timedelta(days=1)
                        attempts += 1
                        
                    if raw_data:
                        try:
                            raw_df = pd.read_csv(io.StringIO(raw_data))
                            cleaned_df = clean_bhavcopy(raw_df)
                            db_df = update_consolidated_database(cleaned_df, db_df)
                            st.success(f"Successfully sync'd {len(cleaned_df)} rows for {current_attempt_date.strftime('%Y-%m-%d')}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error parsing downloaded data: {e}")
                    elif attempt_str in existing_dates:
                        pass
                    else:
                        st.error(f"Could not download trading data for {target_date.strftime('%Y-%m-%d')}. Check NSE status or internet connection.")
                        
        else:
            c_start, c_end = st.columns(2)
            with c_start:
                start_d = st.date_input("Start Date", max_value=max_date)
            with c_end:
                end_d = st.date_input("End Date", max_value=max_date)
                
            if st.button("Sync Date Range", use_container_width=True):
                start_dt = datetime.combine(start_d, datetime.min.time())
                end_dt = datetime.combine(end_d, datetime.min.time())
                
                if start_dt > end_dt:
                    st.error("Start Date cannot be after End Date.")
                else:
                    curr = start_dt
                    target_dates = []
                    existing_dates = set(db_df['Date'].unique()) if not db_df.empty else set()
                    
                    while curr <= end_dt:
                        if curr.date() <= datetime.now().date() and curr.weekday() < 5:
                            if curr.strftime('%Y-%m-%d') not in existing_dates:
                                target_dates.append(curr)
                        curr += timedelta(days=1)
                        
                    if not target_dates:
                        st.info("No missing trading days (weekdays) found in the selected range.")
                    else:
                        st.write(f"Found {len(target_dates)} missing dates. Syncing...")
                        
                        all_cleaned = []
                        prog_bar = st.progress(0)
                        
                        for i, d in enumerate(target_dates):
                            prog_bar.progress((i) / len(target_dates))
                            
                            # Check if local file already exists
                            date_url_str = format_date_for_url(d)
                            filename = f"sec_bhavdata_full_{date_url_str}.csv"
                            filepath = os.path.join(BHAV_DIR, filename)
                            raw_data = None
                            
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                                try:
                                    with open(filepath, 'r', encoding='utf-8') as f:
                                        raw_data = f.read()
                                except Exception as e:
                                    logger.error(f"Error reading local file: {e}")
                                    
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
                                    
                        prog_bar.progress(1.0)
                        
                        if all_cleaned:
                            concatenated = pd.concat(all_cleaned, ignore_index=True)
                            db_df = update_consolidated_database(concatenated, db_df)
                            st.success(f"Range sync complete! Added {len(all_cleaned)} days of data.")
                            st.rerun()
                        else:
                            st.error("Failed to download any new dates in range.")
                            
        st.markdown("### 📤 Export Database")
        if not db_df.empty:
            # We can read the full CSV as a download button stream
            with open(CONSOLIDATED_FILE, 'rb') as f:
                st.download_button(
                    label="Download Consolidated CSV Database",
                    data=f,
                    file_name=f"nse_all_stocks_data_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.button("Database Empty - Nothing to Export", disabled=True, use_container_width=True)
            
    with col2:
        st.markdown("### 🔍 View & Browse Historical Data")
        if not db_df.empty and db_dates:
            selected_view_date = st.selectbox("Select Historical Session Date", db_dates)
            
            df_date = db_df[db_df['Date'] == selected_view_date].copy()
            df_date['Pct_Change'] = ((df_date['Close'] - df_date['Prev_Close']) / df_date['Prev_Close'] * 100).round(2)
            
            st.write(f"Showing session details for: **{selected_view_date}** ({len(df_date):,} stocks found)")
            
            # Quick Stats
            df_valid_price = df_date[df_date['Prev_Close'] > 0]
            top_gainers = df_valid_price.sort_values(by='Pct_Change', ascending=False).head(5)
            top_losers = df_valid_price.sort_values(by='Pct_Change', ascending=True).head(5)
            top_volume = df_date.sort_values(by='Volume', ascending=False).head(5)
            
            # Use inner tabs for each performance category to avoid horizontal squishing
            tab_gain, tab_lose, tab_vol = st.tabs(["🚀 Top Gainers", "🔻 Top Losers", "📊 Top Volume Traded"])
            
            with tab_gain:
                st.dataframe(top_gainers[['Symbol', 'Close', 'Pct_Change']], hide_index=True, use_container_width=True)
            with tab_lose:
                st.dataframe(top_losers[['Symbol', 'Close', 'Pct_Change']], hide_index=True, use_container_width=True)
            with tab_vol:
                st.dataframe(top_volume[['Symbol', 'Close', 'Volume']], hide_index=True, use_container_width=True)
                
            # Table Search and Filter section removed as requested
        else:
            st.info("No data downloaded yet. Download a date to preview records.")

# ----------------- TAB 2: STOCK SCREENER -----------------
with tab_screen:
    st.markdown("### 🔍 Custom Quantitative Stock Screener")
    st.write("Write custom Python screen logic inside the text box below. The script will evaluate historical daily data for all selected tickers and register matches where the screen returns `True` or a matching boolean Series.")
    
    # Left editor, Right controller
    sc1, sc2 = st.columns([2, 1])
    
    # Load strategies
    saved_strategies = load_strategies_from_file()
    strategy_names = [s['name'] for s in saved_strategies]
    
    with sc2:
        st.markdown("#### Configuration & Controls")
        
        # Segment Selection
        segment = st.selectbox(
            "Target Stock Segment",
            ["All Cash Stocks", "Nifty 50", "Nifty 500", "FnO Stocks", "Custom Watchlist (Upload)"],
            index=1
        )
        
        segment_code = "all"
        watchlist_symbols = []
        
        if segment == "Nifty 50":
            segment_code = "nifty50"
        elif segment == "Nifty 500":
            segment_code = "nifty500"
        elif segment == "FnO Stocks":
            segment_code = "fno"
        elif segment == "Custom Watchlist (Upload)":
            segment_code = "watchlist"
            uploaded_file = st.file_uploader("Upload Tickers File (CSV/Excel)", type=["csv", "xls", "xlsx"])
            if uploaded_file:
                try:
                    filename = uploaded_file.name.lower()
                    if filename.endswith('.csv'):
                        up_df = pd.read_csv(uploaded_file)
                    else:
                        up_df = pd.read_excel(uploaded_file)
                        
                    symbol_col = None
                    for col in up_df.columns:
                        if 'SYMBOL' in str(col).upper() or 'TICKER' in str(col).upper():
                            symbol_col = col
                            break
                    if symbol_col is None:
                        symbol_col = up_df.columns[0]
                        
                    watchlist_symbols = up_df[symbol_col].dropna().astype(str).str.strip().str.upper().unique().tolist()
                    watchlist_symbols = [s for s in watchlist_symbols if s]
                    st.success(f"Parsed {len(watchlist_symbols)} unique symbols from watchlist!")
                except Exception as e:
                    st.error(f"Error parsing watchlist: {e}")
                    
        # Strategy selection
        selected_strat_name = st.selectbox("Load Saved Strategy Template", strategy_names)
        selected_strategy = next((s for s in saved_strategies if s['name'] == selected_strat_name), saved_strategies[0])
        
        # Input to save a new strategy
        st.markdown("---")
        st.markdown("##### Save/Update Custom Strategy")
        new_strat_name = st.text_input("Strategy Name", selected_strat_name)
        
    with sc1:
        # Update text area state directly if strategy selection changed
        if st.session_state.get("prev_selected_strat") != selected_strat_name:
            st.session_state["strategy_code_area"] = selected_strategy["code"]
            st.session_state["prev_selected_strat"] = selected_strat_name
            
        code_input = st.text_area(
            "Write screen(df) function code",
            height=400,
            key="strategy_code_area"
        )
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Save/Update Strategy Template", use_container_width=True):
                if new_strat_name.strip() and code_input:
                    if save_strategy(new_strat_name, code_input):
                        st.success(f"Strategy '{new_strat_name}' saved successfully!")
                        st.rerun()
                    else:
                        st.error("Failed to save strategy.")
                else:
                    st.error("Name and code are required.")
                    
        with col_btn2:
            if st.button("🗑️ Delete Selected Strategy Template", use_container_width=True):
                if delete_strategy(selected_strat_name):
                    st.success(f"Strategy '{selected_strat_name}' deleted!")
                    st.rerun()
                else:
                    st.error("Failed to delete strategy.")
                    
    st.markdown("---")
    
    # Run Screener Action
    if st.button("🚀 Run Screener", use_container_width=True, type="primary"):
        if db_df.empty:
            st.error("Database is empty. Please load data first on the Dashboard tab.")
        else:
            with st.spinner("Executing quant screening code across historical database..."):
                res = run_screener_logic(db_df, code_input, segment_code, watchlist_symbols)
                
                if res.get('status') == 'error':
                    st.error(res.get('message'))
                else:
                    hist_res = res.get('historical_results', {})
                    total_matches = sum(len(v) for v in hist_res.values())
                    
                    if total_matches == 0:
                        st.info("Screener execution complete. No stocks matched your strategy criteria.")
                    else:
                        st.success(f"Screening complete! Found **{total_matches}** matching events across **{len(hist_res)}** dates.")
                        
                        # Flat structure for export/dataframe
                        flat_results = []
                        for date_str, items in hist_res.items():
                            for item in items:
                                row = {
                                    "Date": date_str,
                                    "Symbol": item["Symbol"],
                                    "Close": item["Close"],
                                    "Volume": item["Volume"]
                                }
                                flat_results.append(row)
                                
                        df_results = pd.DataFrame(flat_results)
                        df_results = df_results.sort_values(by=["Date", "Symbol"], ascending=[False, True])
                        
                        # Show grouped results in a neat format
                        st.markdown("### 🏆 Screener Matches")
                        
                        # Export Options
                        excel_buffer = io.BytesIO()
                        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                            df_results.to_excel(writer, index=False, sheet_name='Screener Results')
                        excel_data = excel_buffer.getvalue()
                        
                        st.download_button(
                            label="📥 Export Matches to Excel",
                            data=excel_data,
                            file_name=f"screener_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        
                        st.dataframe(df_results, use_container_width=True, hide_index=True)

# ----------------- TAB 3: TICKER TECHNICAL CHART -----------------
with tab_charts:
    st.markdown("### 📈 Interactive Split-Adjusted Historical Stock Chart")
    
    if not db_df.empty:
        all_symbols = sorted(db_df['Symbol'].dropna().unique().tolist())
        selected_symbol = st.selectbox("Search & Select Symbol", all_symbols, index=0)
        
        if selected_symbol:
            # Check splits cache
            splits = get_splits_for_stock(selected_symbol, fetch_online=True)
            
            # Get adjusted stock history
            df_symbol = get_adjusted_df_for_symbol(db_df, selected_symbol)
            
            if df_symbol.empty:
                st.warning(f"No pricing data found for ticker '{selected_symbol}' in the local database.")
            else:
                st.write(f"Displaying adjusted history for **{selected_symbol}** ({len(df_symbol)} sessions)")
                
                # Check for corporate action / split logs
                if splits:
                    st.markdown("##### 📢 Corporate Action: Splits History")
                    split_details = [f"**{dt}**: Ratio {ratio}" for dt, ratio in splits.items()]
                    st.write(", ".join(split_details))
                    
                # Create advanced Plotly Candlestick and Volume subplots
                fig = make_subplots(
                    rows=2, cols=1, 
                    shared_xaxes=True, 
                    vertical_spacing=0.08, 
                    row_heights=[0.7, 0.3]
                )
                
                # Add Candlestick trace
                fig.add_trace(
                    go.Candlestick(
                        x=df_symbol['Date'],
                        open=df_symbol['Open'],
                        high=df_symbol['High'],
                        low=df_symbol['Low'],
                        close=df_symbol['Close'],
                        name="Price",
                        increasing_line_color='#26a69a', 
                        decreasing_line_color='#ef5350'
                    ),
                    row=1, col=1
                )
                
                # Color volume bar based on positive/negative close change
                colors = []
                for idx, row in df_symbol.iterrows():
                    prev_close = row['Prev_Close']
                    colors.append('#26a69a' if row['Close'] >= prev_close else '#ef5350')
                    
                # Add Volume trace
                fig.add_trace(
                    go.Bar(
                        x=df_symbol['Date'],
                        y=df_symbol['Volume'],
                        name="Volume",
                        marker_color=colors,
                        opacity=0.8
                    ),
                    row=2, col=1
                )
                
                fig.update_layout(
                    xaxis_rangeslider_visible=False,
                    height=600,
                    margin=dict(t=20, b=20, l=10, r=10),
                    template="plotly_dark",
                    hovermode="x unified"
                )
                
                fig.update_yaxes(title_text="Price (INR)", row=1, col=1)
                fig.update_yaxes(title_text="Volume", row=2, col=1)
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Raw Table view
                with st.expander("View Raw Adjusted Data Table"):
                    st.dataframe(df_symbol.sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("No data available in database to plot charts. Please download data first.")

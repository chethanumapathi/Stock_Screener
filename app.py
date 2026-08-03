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
from flask import Flask, jsonify, request, render_template, send_file

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BHAV_DIR = os.path.join(DATA_DIR, 'bhavcopies')
CONSOLIDATED_FILE = os.path.join(DATA_DIR, 'consolidated_data.csv')

# Global DataFrame Cache
DB_DF = None
ADJUSTED_DF_CACHE = {}

def load_database_into_memory():
    global DB_DF
    if os.path.exists(CONSOLIDATED_FILE) and os.path.getsize(CONSOLIDATED_FILE) > 0:
        try:
            logger.info("Loading consolidated database into memory...")
            start_time = time.time()
            df = pd.read_csv(CONSOLIDATED_FILE)
            df['Date'] = df['Date'].astype(str)
            df['Symbol'] = df['Symbol'].astype(str)
            # Ensure sorting
            df = df.sort_values(by=['Date', 'Symbol'], ascending=[False, True])
            DB_DF = df
            ADJUSTED_DF_CACHE.clear()
            logger.info(f"Loaded {len(DB_DF)} records in {time.time() - start_time:.2f} seconds.")
        except Exception as e:
            logger.error(f"Error loading database into memory: {e}")
            DB_DF = pd.DataFrame()
    else:
        DB_DF = pd.DataFrame()

# Load database on startup
load_database_into_memory()

# Splits Cache Constants and Helpers
SPLITS_CACHE_FILE = os.path.join(DATA_DIR, 'splits_cache.json')
SPLITS_CACHE = {}

def load_splits_cache():
    global SPLITS_CACHE
    if os.path.exists(SPLITS_CACHE_FILE) and os.path.getsize(SPLITS_CACHE_FILE) > 0:
        try:
            with open(SPLITS_CACHE_FILE, 'r') as f:
                SPLITS_CACHE = json.load(f)
            logger.info(f"Loaded splits cache with {len(SPLITS_CACHE)} symbols.")
        except Exception as e:
            logger.error(f"Error loading splits cache: {e}")
            SPLITS_CACHE = {}
    else:
        SPLITS_CACHE = {}

def get_splits_for_stock(symbol, fetch_online=True):
    global SPLITS_CACHE
    symbol = symbol.upper()
    if symbol in SPLITS_CACHE:
        return SPLITS_CACHE[symbol]
        
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
        SPLITS_CACHE[symbol] = splits_dict
        # Save cache file
        with open(SPLITS_CACHE_FILE, 'w') as f:
            json.dump(SPLITS_CACHE, f)
    except Exception as e:
        logger.error(f"Error fetching splits for {symbol}: {e}")
        # Return empty but don't cache permanently to allow retrying
        return {}
    return splits_dict

def adjust_for_splits(df_symbol, splits_dict):
    if not splits_dict or df_symbol.empty:
        return df_symbol
        
    df_adj = df_symbol.copy()
    # Sort splits by date ascending
    sorted_splits = sorted(splits_dict.items(), key=lambda x: x[0])
    
    for split_date, ratio in sorted_splits:
        if ratio <= 0 or ratio == 1.0:
            continue
        # Apply adjustment to all rows before split_date
        mask = df_adj['Date'] < split_date
        if mask.any():
            for col in ['Open', 'High', 'Low', 'Close', 'Prev_Close', 'Avg_Price']:
                if col in df_adj.columns:
                    df_adj.loc[mask, col] = (df_adj.loc[mask, col] / ratio).round(2)
            if 'Volume' in df_adj.columns:
                df_adj.loc[mask, 'Volume'] = (df_adj.loc[mask, 'Volume'] * ratio).round(0)
                
    return df_adj

def get_adjusted_df_for_symbol(symbol):
    global ADJUSTED_DF_CACHE, DB_DF
    symbol = symbol.upper()
    if symbol in ADJUSTED_DF_CACHE:
        return ADJUSTED_DF_CACHE[symbol]
        
    if DB_DF is None or DB_DF.empty:
        return pd.DataFrame()
        
    df_symbol = DB_DF[DB_DF['Symbol'] == symbol]
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
    
    ADJUSTED_DF_CACHE[symbol] = df_symbol
    return df_symbol

# Load splits cache on startup
load_splits_cache()

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

def format_date_for_url(date_obj):
    return date_obj.strftime("%d%m%Y")

def format_date_to_db(date_str):
    # Converts '31-Jul-2026' or '31-JUL-2026' to '2026-07-31'
    # Or returns raw if already YYYY-MM-DD
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
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()
    
    # Check if required columns exist, mapping them
    mapped_cols = {}
    for raw_col, clean_col in COLUMN_MAP.items():
        if raw_col in df.columns:
            mapped_cols[raw_col] = clean_col
            
    df = df.rename(columns=mapped_cols)
    
    # Strip string values
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()
        
    # Standardize series
    if 'Series' in df.columns:
        df = df[df['Series'].isin(['EQ', 'BE', 'SM'])]
        
    # Parse dates to YYYY-MM-DD
    if 'Date' in df.columns:
        df['Date'] = df['Date'].apply(format_date_to_db)
        
    # Standardize numeric columns
    numeric_cols = ['Prev_Close', 'Open', 'High', 'Low', 'Last', 'Close', 'Avg_Price', 
                    'Volume', 'Turnover_Lacs', 'No_Of_Trades', 'Deliv_Qty', 'Deliv_Per']
    
    for col in numeric_cols:
        if col in df.columns:
            # Clean non-numeric characters like spaces or '-'
            df[col] = df[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
    # Reorder columns to a clean layout
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
    # Establish session cookies
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
    # Save the raw file for history
    filename = f"sec_bhavdata_full_{format_date_for_url(date_obj)}.csv"
    filepath = os.path.join(BHAV_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(raw_csv_text)
    logger.info(f"Saved daily raw file to {filepath}")
    return filepath

def update_consolidated_database(cleaned_df):
    global DB_DF
    if cleaned_df.empty:
        return len(DB_DF) if DB_DF is not None else 0
        
    new_dates = cleaned_df['Date'].unique()
    
    if DB_DF is not None and not DB_DF.empty:
        # Filter out existing data for these dates
        DB_DF = DB_DF[~DB_DF['Date'].isin(new_dates)]
    else:
        DB_DF = pd.DataFrame(columns=cleaned_df.columns)
        
    # Append new data
    DB_DF = pd.concat([DB_DF, cleaned_df], ignore_index=True)
    DB_DF = DB_DF.sort_values(by=['Date', 'Symbol'], ascending=[False, True])
    
    # Save to file
    try:
        DB_DF.to_csv(CONSOLIDATED_FILE, index=False)
        ADJUSTED_DF_CACHE.clear()  # Clear cache to invalidate stale adjusted DataFrames
        logger.info(f"Database updated in-memory and saved. Total records: {len(DB_DF)}")
    except Exception as e:
        logger.error(f"Failed to write database file: {e}")
        
    return len(DB_DF)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/download', methods=['POST'])
def download_data():
    req_data = request.json or {}
    date_str = req_data.get('date') # Format YYYY-MM-DD
    from_date_str = req_data.get('from_date')
    to_date_str = req_data.get('to_date')
    fallback = req_data.get('fallback', True)
    
    if from_date_str and to_date_str:
        try:
            from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
            to_date = datetime.strptime(to_date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"status": "error", "message": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                return jsonify({"status": "error", "message": "Invalid date format. Use YYYY-MM-DD"}), 400
        else:
            target_date = datetime.now()
        from_date = target_date
        to_date = target_date

    # Limit future dates
    if from_date.date() > datetime.now().date():
        return jsonify({"status": "error", "message": "Cannot download data for future dates."}), 400
    if to_date.date() > datetime.now().date():
        to_date = datetime.now() # Caps at today
        
    if from_date > to_date:
        return jsonify({"status": "error", "message": "From Date cannot be after To Date."}), 400
        
    # Get existing dates in DB
    existing_dates = set()
    if DB_DF is not None and not DB_DF.empty:
        existing_dates = set(DB_DF['Date'].unique())
        
    # If downloading a range (from_date != to_date)
    is_range = (from_date.date() != to_date.date())
    
    if is_range:
        # Generate target weekdays in range
        curr = from_date
        target_dates = []
        while curr <= to_date:
            if curr.date() <= datetime.now().date() and curr.weekday() < 5:
                target_dates.append(curr)
            curr += timedelta(days=1)
            
        if not target_dates:
            return jsonify({"status": "error", "message": "No trading days (weekdays) found in the selected range."}), 400
            
        # Check if all target dates are already in DB
        missing_dates = [d for d in target_dates if d.strftime('%Y-%m-%d') not in existing_dates]
        
        if not missing_dates:
            return jsonify({
                "status": "already_exists",
                "message": "Data for the selected date range is already available in the database."
            })
            
        # Download missing dates
        all_cleaned_dfs = []
        downloaded_dates = []
        for d in missing_dates:
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
                    cleaned_df = clean_bhavcopy(raw_df)
                    if not cleaned_df.empty:
                        all_cleaned_dfs.append(cleaned_df)
                        downloaded_dates.append(d.strftime('%Y-%m-%d'))
                except Exception as e:
                    logger.error(f"Error parsing data for {d.strftime('%Y-%m-%d')}: {e}")
                    
        if not all_cleaned_dfs:
            return jsonify({
                "status": "error",
                "message": "Failed to download data for any of the missing dates. Markets might be closed or NSE is unavailable."
            }), 404
            
        concatenated_df = pd.concat(all_cleaned_dfs, ignore_index=True)
        total_db_records = update_consolidated_database(concatenated_df)
        
        # Take stats of the latest downloaded date in the range
        latest_df = all_cleaned_dfs[-1]
        latest_date_str = downloaded_dates[-1]
        
        gains = []
        losses = []
        high_volume = []
        if not latest_df.empty:
            df_stats = latest_df.copy()
            df_stats['Pct_Change'] = ((df_stats['Close'] - df_stats['Prev_Close']) / df_stats['Prev_Close'] * 100).round(2)
            df_valid_price = df_stats[df_stats['Prev_Close'] > 0]
            top_gainers = df_valid_price.sort_values(by='Pct_Change', ascending=False).head(5)
            top_losers = df_valid_price.sort_values(by='Pct_Change', ascending=True).head(5)
            top_vol = df_stats.sort_values(by='Volume', ascending=False).head(5)
            gains = top_gainers[['Symbol', 'Close', 'Pct_Change']].to_dict(orient='records')
            losses = top_losers[['Symbol', 'Close', 'Pct_Change']].to_dict(orient='records')
            high_volume = top_vol[['Symbol', 'Close', 'Volume']].to_dict(orient='records')
            
        return jsonify({
            "status": "success",
            "date": latest_date_str,
            "records_downloaded": sum(len(df) for df in all_cleaned_dfs),
            "total_database_records": total_db_records,
            "downloaded_dates": downloaded_dates,
            "stats": {
                "top_gainers": gains,
                "top_losers": losses,
                "high_volume": high_volume
            }
        })
        
    else:
        # Single date download logic (supports backtracking)
        current_attempt_date = from_date
        raw_data = None
        attempts = 0
        max_attempts = 7 if fallback else 1
        
        while attempts < max_attempts:
            if current_attempt_date.weekday() < 5:
                attempt_str = current_attempt_date.strftime('%Y-%m-%d')
                if attempt_str in existing_dates:
                    return jsonify({
                        "status": "already_exists",
                        "message": f"Data for {attempt_str} is already available."
                    })
                
                date_url_str = format_date_for_url(current_attempt_date)
                filename = f"sec_bhavdata_full_{date_url_str}.csv"
                filepath = os.path.join(BHAV_DIR, filename)
                
                if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            raw_data = f.read()
                    except Exception as e:
                        logger.error(f"Error reading local file: {e}")
                
                if not raw_data:
                    raw_data = download_bhavcopy_from_nse(current_attempt_date)
                    if raw_data:
                        save_daily_bhav(current_attempt_date, raw_data)
                        
                if raw_data:
                    break
            current_attempt_date -= timedelta(days=1)
            attempts += 1
            
        if not raw_data:
            formatted_target = from_date.strftime('%Y-%m-%d')
            return jsonify({
                "status": "error",
                "message": f"Could not find any trading data for {formatted_target} or the preceding week."
            }), 404
            
        try:
            raw_df = pd.read_csv(io.StringIO(raw_data))
            cleaned_df = clean_bhavcopy(raw_df)
            total_db_records = update_consolidated_database(cleaned_df)
        except Exception as e:
            logger.error(f"Error parsing downloaded data: {e}")
            return jsonify({"status": "error", "message": f"Error parsing data: {str(e)}"}), 500
            
        gains = []
        losses = []
        high_volume = []
        if not cleaned_df.empty:
            df_stats = cleaned_df.copy()
            df_stats['Pct_Change'] = ((df_stats['Close'] - df_stats['Prev_Close']) / df_stats['Prev_Close'] * 100).round(2)
            df_valid_price = df_stats[df_stats['Prev_Close'] > 0]
            top_gainers = df_valid_price.sort_values(by='Pct_Change', ascending=False).head(5)
            top_losers = df_valid_price.sort_values(by='Pct_Change', ascending=True).head(5)
            top_vol = df_stats.sort_values(by='Volume', ascending=False).head(5)
            gains = top_gainers[['Symbol', 'Close', 'Pct_Change']].to_dict(orient='records')
            losses = top_losers[['Symbol', 'Close', 'Pct_Change']].to_dict(orient='records')
            high_volume = top_vol[['Symbol', 'Close', 'Volume']].to_dict(orient='records')
            
        return jsonify({
            "status": "success",
            "date": current_attempt_date.strftime("%Y-%m-%d"),
            "records_downloaded": len(cleaned_df),
            "total_database_records": total_db_records,
            "backtracked_days": attempts,
            "stats": {
                "top_gainers": gains,
                "top_losers": losses,
                "high_volume": high_volume
            }
        })

@app.route('/api/history', methods=['GET'])
def get_history():
    global DB_DF
    history_dates = []
    total_records = 0
    last_updated = "Never"
    
    if DB_DF is not None and not DB_DF.empty:
        total_records = len(DB_DF)
        unique_dates = DB_DF['Date'].unique().tolist()
        history_dates = sorted(unique_dates, reverse=True)
        if history_dates:
            last_updated = history_dates[0]
            
    # Also find files in directory to cross reference
    files = []
    if os.path.exists(BHAV_DIR):
        for f in os.listdir(BHAV_DIR):
            if f.startswith("sec_bhavdata_full_") and f.endswith(".csv"):
                # Extract date
                match = re.search(r'sec_bhavdata_full_(\d{2})(\d{2})(\d{4})\.csv', f)
                if match:
                    d, m, y = match.groups()
                    db_date = f"{y}-{m}-{d}"
                    if db_date not in files:
                        files.append(db_date)
                        
    # Combine lists and clean
    combined_dates = sorted(list(set(history_dates + files)), reverse=True)
    
    return jsonify({
        "total_records": total_records,
        "last_updated": last_updated,
        "downloaded_dates": combined_dates
    })

@app.route('/api/view_data', methods=['GET'])
def view_data():
    global DB_DF
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"status": "error", "message": "Missing date parameter"}), 400
        
    # Read from in-memory cache
    if DB_DF is not None and not DB_DF.empty:
        try:
            df_date = DB_DF[DB_DF['Date'] == date_str]
            if not df_date.empty:
                # Calculate percent change on the fly for preview
                df_date = df_date.copy()
                df_date['Pct_Change'] = ((df_date['Close'] - df_date['Prev_Close']) / df_date['Prev_Close'] * 100).round(2)
                
                # Fetch preview (top 100 records for speed)
                preview_data = df_date.head(100).to_dict(orient='records')
                total_records = len(df_date)
                
                # Top performers for stats
                df_valid_price = df_date[df_date['Prev_Close'] > 0]
                gains = df_valid_price.sort_values(by='Pct_Change', ascending=False).head(5)[['Symbol', 'Close', 'Pct_Change']].to_dict(orient='records')
                losses = df_valid_price.sort_values(by='Pct_Change', ascending=True).head(5)[['Symbol', 'Close', 'Pct_Change']].to_dict(orient='records')
                high_volume = df_date.sort_values(by='Volume', ascending=False).head(5)[['Symbol', 'Close', 'Volume']].to_dict(orient='records')
                
                return jsonify({
                    "status": "success",
                    "date": date_str,
                    "total_records": total_records,
                    "data": preview_data,
                    "stats": {
                        "top_gainers": gains,
                        "top_losers": losses,
                        "high_volume": high_volume
                    }
                })
        except Exception as e:
            logger.error(f"Error reading from database: {e}")
            
    # Try reading from daily file as backup
    filename = f"sec_bhavdata_full_{date_str[8:10]}{date_str[5:7]}{date_str[0:4]}.csv"
    filepath = os.path.join(BHAV_DIR, filename)
    if os.path.exists(filepath):
        try:
            raw_df = pd.read_csv(filepath)
            cleaned_df = clean_bhavcopy(raw_df)
            cleaned_df['Pct_Change'] = ((cleaned_df['Close'] - cleaned_df['Prev_Close']) / cleaned_df['Prev_Close'] * 100).round(2)
            preview_data = cleaned_df.head(100).to_dict(orient='records')
            
            df_valid_price = cleaned_df[cleaned_df['Prev_Close'] > 0]
            gains = df_valid_price.sort_values(by='Pct_Change', ascending=False).head(5)[['Symbol', 'Close', 'Pct_Change']].to_dict(orient='records')
            losses = df_valid_price.sort_values(by='Pct_Change', ascending=True).head(5)[['Symbol', 'Close', 'Pct_Change']].to_dict(orient='records')
            high_volume = cleaned_df.sort_values(by='Volume', ascending=False).head(5)[['Symbol', 'Close', 'Volume']].to_dict(orient='records')
            
            return jsonify({
                "status": "success",
                "date": date_str,
                "total_records": len(cleaned_df),
                "data": preview_data,
                "stats": {
                    "top_gainers": gains,
                    "top_losers": losses,
                    "high_volume": high_volume
                }
            })
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error reading daily file: {str(e)}"}), 500
            
    return jsonify({"status": "error", "message": "No data found for this date."}), 404

@app.route('/api/stocks', methods=['GET'])
def get_stocks():
    global DB_DF
    if DB_DF is not None and not DB_DF.empty:
        # Get sorted list of unique symbols
        symbols = sorted(DB_DF['Symbol'].dropna().unique().tolist())
        return jsonify({"status": "success", "symbols": symbols})
    return jsonify({"status": "success", "symbols": []})

@app.route('/api/stock/<symbol>', methods=['GET'])
def get_stock_data(symbol):
    global DB_DF
    if DB_DF is not None and not DB_DF.empty:
        # Pre-fetch splits online for single stock charts
        get_splits_for_stock(symbol, fetch_online=True)
        df_symbol = get_adjusted_df_for_symbol(symbol)
        if not df_symbol.empty:
            chart_data = []
            for _, r in df_symbol.iterrows():
                chart_data.append({
                    'time': r['Date'],
                    'open': float(r['Open']),
                    'high': float(r['High']),
                    'low': float(r['Low']),
                    'close': float(r['Close']),
                    'volume': float(r['Volume'])
                })
            return jsonify({
                "status": "success",
                "symbol": symbol.upper(),
                "data": chart_data
            })
    return jsonify({"status": "error", "message": f"No data found for symbol {symbol}"}), 404

@app.route('/api/export', methods=['GET'])
def export_database():
    if os.path.exists(CONSOLIDATED_FILE) and os.path.getsize(CONSOLIDATED_FILE) > 0:
        try:
            return send_file(
                CONSOLIDATED_FILE,
                mimetype='text/csv',
                as_attachment=True,
                download_name=f"nse_all_stocks_data_{datetime.now().strftime('%Y%m%d')}.csv"
            )
        except Exception as e:
            return jsonify({"status": "error", "message": f"Export error: {str(e)}"}), 500
    else:
        return jsonify({"status": "error", "message": "Database is empty. Please download data first."}), 404

# --- Stock Screener Logic and Routes ---
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
            
    # Download and cache
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
        
    # Hardcoded fallback
    return ['ADANIENT', 'ADANIPORTS', 'APOLLOHOSP', 'ASIANPAINT', 'AXISBANK', 'BAJAJ-AUTO', 'BAJFINANCE', 'BAJAJFINSV', 'BHARTIARTL', 'BPCL', 'BRITANNIA', 'CIPLA', 'COALINDIA', 'DIVISLAB', 'DRREDDY', 'EICHERMOT', 'GRASIM', 'HCLTECH', 'HDFCBANK', 'HDFCLIFE', 'HEROMOTOCO', 'HINDALCO', 'HINDUNILVR', 'ICICIBANK', 'INDUSINDBK', 'INFY', 'ITC', 'JSWSTEEL', 'KOTAKBANK', 'LT', 'LTIM', 'M&M', 'MARUTI', 'NESTLEIND', 'NTPC', 'ONGC', 'POWERGRID', 'RELIANCE', 'SBILIFE', 'SBIN', 'SUNPHARMA', 'TATACONSUM', 'TATAMOTORS', 'TATASTEEL', 'TCS', 'TECHM', 'TITAN', 'ULTRACEMCO', 'WIPRO']

def fetch_nifty500_symbols():
    if os.path.exists(NIFTY500_FILE) and os.path.getsize(NIFTY500_FILE) > 0:
        try:
            df = pd.read_csv(NIFTY500_FILE)
            return df['Symbol'].dropna().str.strip().tolist()
        except Exception as e:
            logger.error(f"Error reading local Nifty 500 file: {e}")
            
    # Download and cache
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
            
    # Download and cache
    try:
        logger.info("Downloading FnO constituents list...")
        url = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = df.columns.str.strip()
            # Find UNDERLYING col
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

def run_screener_logic(code_str, segment, watchlist_symbols=None):
    # Segment symbol filter
    symbols = []
    if segment == 'nifty50':
        symbols = fetch_nifty50_symbols()
    elif segment == 'nifty500':
        symbols = fetch_nifty500_symbols()
    elif segment == 'fno':
        symbols = fetch_fno_symbols()
    elif segment == 'watchlist' and watchlist_symbols:
        symbols = watchlist_symbols
    else: # cash/all segment
        if DB_DF is not None and not DB_DF.empty:
            symbols = DB_DF['Symbol'].dropna().unique().tolist()
            
    # Filter symbols by what is actually present in DB_DF
    if DB_DF is not None and not DB_DF.empty:
        db_symbols = set(DB_DF['Symbol'].unique())
        symbols = [s for s in symbols if s in db_symbols]
        
    results = []
    
    # Compile the code
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
    
    for symbol in symbols:
        df_symbol = get_adjusted_df_for_symbol(symbol)
        if df_symbol.empty:
            continue
        
        try:
            res = screen_func(df_symbol)
            
            # Determine if res is a Series or a dictionary of Series
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
                    # Broadcast single value (standard Python bool) to the last element
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
                            # Broadcast single value
                            custom_series[k] = pd.Series([v] * len(df_symbol), index=df_symbol.index)
            elif isinstance(res, (bool, np.bool_)):
                # Single boolean: evaluate on the last element only
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
                
            # Find indices where signal is True
            match_indices = df_symbol.index[signal_series == True]
            for idx in match_indices:
                row = df_symbol.loc[idx]
                date_str = row['Date']
                
                custom_data = {}
                for k, s_val in custom_series.items():
                    custom_data[k] = s_val.loc[idx]
                    # Handle NumPy conversions
                    if hasattr(custom_data[k], 'item'):
                        custom_data[k] = custom_data[k].item()
                
                # Compute Pct_Change relative to previous chronological session
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
            
    # Count total matches across history
    total_matches = sum(len(v) for v in historical_results.values())
    logger.info(f"Screening complete. Found {total_matches} matches across {len(historical_results)} dates in {time.time() - start_time:.2f} seconds.")
    return {"status": "success", "historical_results": historical_results}

@app.route('/api/screener/parse_watchlist', methods=['POST'])
def parse_watchlist():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Empty file name"}), 400
        
    try:
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file)
        else:
            return jsonify({"status": "error", "message": "Unsupported file format. Please upload Excel (.xls, .xlsx) or CSV."}), 400
            
        # Find Symbol column case-insensitive
        symbol_col = None
        for col in df.columns:
            if 'SYMBOL' in str(col).upper() or 'TICKER' in str(col).upper():
                symbol_col = col
                break
        if symbol_col is None:
            symbol_col = df.columns[0]
            
        symbols = df[symbol_col].dropna().astype(str).str.strip().str.upper().unique().tolist()
        symbols = [s for s in symbols if s]
        return jsonify({"status": "success", "symbols": symbols})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error parsing watchlist: {str(e)}"}), 500

@app.route('/api/screener/run', methods=['POST'])
def run_screener():
    try:
        data = request.get_json() or {}
        code_str = data.get('code', '')
        segment = data.get('segment', 'all')
        watchlist_symbols = data.get('watchlist', None)
        
        if not code_str:
            return jsonify({"status": "error", "message": "No code provided"}), 400
            
        res = run_screener_logic(code_str, segment, watchlist_symbols)
        return jsonify(res)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Screener execution error: {str(e)}"}), 500

STRATEGIES_FILE = os.path.join(DATA_DIR, 'strategies.json')

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
    # Write default templates if not exist
    try:
        with open(STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_STRATEGIES, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving default strategies: {e}")
    return DEFAULT_STRATEGIES

@app.route('/api/screener/strategies', methods=['GET'])
def get_strategies():
    strategies = load_strategies_from_file()
    return jsonify({"status": "success", "strategies": strategies})

@app.route('/api/screener/strategies', methods=['POST'])
def save_strategy():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    code = data.get('code', '')
    
    if not name or not code:
        return jsonify({"status": "error", "message": "Name and code are required."}), 400
        
    strategies = load_strategies_from_file()
    # Check if exists and update, or append new
    found = False
    for s in strategies:
        if s['name'].lower() == name.lower():
            s['name'] = name # Preserve casing
            s['code'] = code
            found = True
            break
            
    if not found:
        strategies.append({"name": name, "code": code})
        
    try:
        with open(STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(strategies, f, indent=4)
        return jsonify({"status": "success", "message": f"Strategy '{name}' saved successfully."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to save strategy: {str(e)}"}), 500

@app.route('/api/screener/strategies/<name>', methods=['DELETE'])
def delete_strategy(name):
    strategies = load_strategies_from_file()
    updated = [s for s in strategies if s['name'].lower() != name.lower()]
    
    if len(updated) == len(strategies):
        return jsonify({"status": "error", "message": f"Strategy '{name}' not found."}), 404
        
    try:
        with open(STRATEGIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(updated, f, indent=4)
        return jsonify({"status": "success", "message": f"Strategy '{name}' deleted successfully."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to delete strategy: {str(e)}"}), 500

@app.route('/api/screener/export', methods=['POST'])
def export_screener_results():
    try:
        req_data = request.json or {}
        date_str = req_data.get('date', 'all')
        results = req_data.get('results', [])
        
        if not results:
            return jsonify({"status": "error", "message": "No results to export"}), 400
            
        df = pd.DataFrame(results)
        
        # Order columns logically
        base_cols = ['Symbol', 'Close', 'Pct_Change', 'Volume']
        existing_base_cols = [c for c in base_cols if c in df.columns]
        other_cols = [c for c in df.columns if c not in existing_base_cols]
        df = df[existing_base_cols + other_cols]
        
        output = io.BytesIO()
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        filename = f"screener_results_{date_str}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
        try:
            # Attempt to use openpyxl / xlsxwriter for standard Excel
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Screener Results')
            output.seek(0)
        except Exception:
            try:
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Screener Results')
                output.seek(0)
            except Exception:
                # Fallback to CSV
                csv_str = df.to_csv(index=False)
                output.write(csv_str.encode('utf-8'))
                output.seek(0)
                mimetype = 'text/csv'
                filename = f"screener_results_{date_str}_{datetime.now().strftime('%Y%m%d')}.csv"
                
        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Screener export error: {e}")
        return jsonify({"status": "error", "message": f"Export failed: {str(e)}"}), 500

if __name__ == '__main__':
    # Initialize folder structures double check
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BHAV_DIR, exist_ok=True)
    
    logger.info("Starting Flask application on port 5000...")
    app.run(debug=True, host='0.0.0.0', port=5000)

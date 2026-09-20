"""
build_daily_cache.py
====================
Pre-computes and caches 100% corporate action / split-adjusted daily (EOD)
Parquet files into `data/adjusted_daily/{SYMBOL}.parquet`.

Decouples daily screening and backtesting from heavy raw 1-minute broker tick files,
providing 10x faster execution without modifying or corrupting the pristine raw files in
`C:\\Zerodha Historical Data`.
"""

import os
import sys
import time
import logging
import argparse
import duckdb
import pandas as pd
import numpy as np
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("build_daily_cache")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ADJUSTED_DAILY_DIR = os.path.join(DATA_DIR, 'adjusted_daily')
ZERODHA_MINUTE_DIR = r"C:\Zerodha Historical Data\data\minute"
SPLITS_CACHE_FILE = os.path.join(DATA_DIR, 'splits_cache.json')
NIFTY50_FILE = os.path.join(DATA_DIR, 'nifty50.csv')
NIFTY500_FILE = os.path.join(DATA_DIR, 'nifty500.csv')

# Ensure directories exist
os.makedirs(ADJUSTED_DAILY_DIR, exist_ok=True)


def get_raw_minute_parquet_path(symbol: str) -> str:
    """Returns path to raw 1-minute parquet file if it exists."""
    clean_sym = symbol.upper().replace('.NS', '').strip()
    path = os.path.join(ZERODHA_MINUTE_DIR, f"{clean_sym}.parquet")
    if os.path.exists(path):
        return path
    alt_path1 = os.path.join(DATA_DIR, 'minute', f"{clean_sym}.parquet")
    if os.path.exists(alt_path1):
        return alt_path1
    alt_path2 = os.path.join(DATA_DIR, 'parquet', f"{clean_sym}.parquet")
    if os.path.exists(alt_path2):
        return alt_path2
    return None


def get_daily_cache_path(symbol: str) -> str:
    """Returns destination path for pre-adjusted daily parquet file."""
    clean_sym = symbol.upper().replace('.NS', '').strip()
    return os.path.join(ADJUSTED_DAILY_DIR, f"{clean_sym}.parquet")


def load_splits_cache() -> dict:
    """Loads cached corporate action splits."""
    if os.path.exists(SPLITS_CACHE_FILE):
        try:
            import json
            with open(SPLITS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading splits cache: {e}")
    return {}


def apply_splits_to_daily_df(df: pd.DataFrame, symbol: str, splits_cache: dict = None) -> pd.DataFrame:
    """
    Applies split adjustments to aggregated daily DataFrame.
    Inspects price continuity around split dates to avoid double adjustment.
    Also resolves data stitch seam discontinuities (2023-09-12 vs 2023-09-13)
    where older Kotak data was unadjusted while newer Zerodha data was already split-adjusted.
    """
    if df.empty:
        return df

    if splits_cache is None:
        splits_cache = load_splits_cache()

    symbol = symbol.upper().strip()
    splits = splits_cache.get(symbol, {})
    if not splits:
        return df

    df_adj = df.copy()
    if 'date' in df_adj.columns:
        df_adj['date_str'] = df_adj['date'].astype(str).str.slice(0, 10)
    else:
        return df_adj

    sorted_splits = sorted(splits.items(), key=lambda x: x[0], reverse=True)

    for split_date, ratio in sorted_splits:
        try:
            ratio = float(ratio)
        except (ValueError, TypeError):
            continue

        if ratio <= 0 or ratio == 1.0:
            continue

        mask_before = df_adj['date_str'] < split_date
        mask_after = df_adj['date_str'] >= split_date

        if not mask_before.any() or not mask_after.any():
            continue

        c_before = df_adj.loc[mask_before, 'close'].iloc[-1]
        c_after = df_adj.loc[mask_after, 'close'].iloc[0]
        observed_ratio = (c_before / c_after) if c_after > 0 else 1.0

        # Check if pre-split price reflects the split discontinuity
        if abs(observed_ratio - ratio) < (0.25 * ratio):
            for col in ['open', 'high', 'low', 'close']:
                if col in df_adj.columns:
                    df_adj.loc[mask_before, col] = (df_adj.loc[mask_before, col] / ratio).round(2)
            if 'volume' in df_adj.columns:
                df_adj.loc[mask_before, 'volume'] = (df_adj.loc[mask_before, 'volume'] * ratio).round(0)

    # Secondary check: If a corporate action occurred on or after the data stitch boundary (2023-09-13),
    # Zerodha's feed already retrospectively adjusted post-2023-09-13 data, leaving the pre-2023-09-13
    # Kotak feed unadjusted. Detect and fix this stitch seam discontinuity.
    mask_seam_before = df_adj['date_str'] <= '2023-09-12'
    mask_seam_after = df_adj['date_str'] >= '2023-09-13'
    if mask_seam_before.any() and mask_seam_after.any():
        c_seam_before = df_adj.loc[mask_seam_before, 'close'].iloc[-1]
        c_seam_after = df_adj.loc[mask_seam_after, 'close'].iloc[0]
        if c_seam_after > 0:
            seam_ratio = c_seam_before / c_seam_after
            for split_date, ratio in sorted_splits:
                ratio = float(ratio)
                if split_date >= '2023-09-13' and abs(seam_ratio - ratio) < (0.25 * ratio):
                    for col in ['open', 'high', 'low', 'close']:
                        if col in df_adj.columns:
                            df_adj.loc[mask_seam_before, col] = (df_adj.loc[mask_seam_before, col] / ratio).round(2)
                    if 'volume' in df_adj.columns:
                        df_adj.loc[mask_seam_before, 'volume'] = (df_adj.loc[mask_seam_before, 'volume'] * ratio).round(0)
                    break

    df_adj = df_adj.drop(columns=['date_str'], errors='ignore')
    return df_adj


def build_single_stock_daily_cache(symbol: str, force: bool = False, con: duckdb.DuckDBPyConnection = None, splits_cache: dict = None) -> str:
    """
    Aggregates 1-minute data to daily, applies split adjustments, and saves to
    `data/adjusted_daily/{SYMBOL}.parquet`.
    Returns status: 'cached', 'created', 'updated', or 'skipped'.
    """
    clean_sym = symbol.upper().replace('.NS', '').strip()
    raw_path = get_raw_minute_parquet_path(clean_sym)
    if not raw_path:
        return "skipped"

    out_path = get_daily_cache_path(clean_sym)

    # Incremental check: if daily cache exists and is newer than raw minute file, skip
    if not force and os.path.exists(out_path):
        try:
            raw_mtime = os.path.getmtime(raw_path)
            cache_mtime = os.path.getmtime(out_path)
            if cache_mtime >= raw_mtime:
                return "cached"
        except Exception:
            pass

    owns_con = False
    if con is None:
        con = duckdb.connect()
        owns_con = True

    try:
        norm_path = raw_path.replace('\\', '/')
        sql = """
            SELECT 
                CAST(date AS DATE) AS date,
                FIRST(open) AS open,
                MAX(high) AS high,
                MIN(low) AS low,
                LAST(close) AS close,
                SUM(volume) AS volume
            FROM read_parquet(?)
            GROUP BY 1
            ORDER BY 1 ASC
        """
        df = con.execute(sql, [norm_path]).fetchdf()

        if df.empty:
            return "skipped"

        # Standardize columns
        df['open'] = df['open'].round(2)
        df['high'] = df['high'].round(2)
        df['low'] = df['low'].round(2)
        df['close'] = df['close'].round(2)
        df['volume'] = df['volume'].round(0).astype('int64', errors='ignore')

        # Apply corporate actions splits
        df = apply_splits_to_daily_df(df, clean_sym, splits_cache=splits_cache)

        # Pre-compute Prev_Close smoothly
        df['prev_close'] = df['close'].shift(1).fillna(df['open']).round(2)
        df['symbol'] = clean_sym

        # Save to Parquet
        df.to_parquet(out_path, index=False, compression='snappy')
        return "created" if not os.path.exists(out_path) else "updated"

    except Exception as e:
        logger.error(f"Error building daily cache for {clean_sym}: {e}")
        return "error"
    finally:
        if owns_con:
            try:
                con.close()
            except Exception:
                pass


def build_daily_cache_batch(symbols: list, force: bool = False, progress_callback=None) -> dict:
    """
    Builds pre-adjusted daily cache for a batch of symbols.
    Calls progress_callback(current, total, symbol, status) if provided.
    """
    symbols = [s.upper().replace('.NS', '').strip() for s in symbols if s and str(s).strip()]
    total = len(symbols)
    logger.info(f"Starting daily cache build for {total} stocks (force={force})...")

    splits_cache = load_splits_cache()
    con = duckdb.connect()

    stats = {"created": 0, "updated": 0, "cached": 0, "skipped": 0, "error": 0, "total": total}

    try:
        for i, sym in enumerate(symbols):
            status = build_single_stock_daily_cache(sym, force=force, con=con, splits_cache=splits_cache)
            if status in stats:
                stats[status] += 1
            else:
                stats["skipped"] += 1

            if progress_callback:
                progress_callback(i + 1, total, sym, status)

            if (i + 1) % 50 == 0 or (i + 1) == total:
                logger.info(f"Daily Cache Progress: {i + 1}/{total} - {stats['created'] + stats['updated']} built, {stats['cached']} cached, {stats['skipped']} skipped")

    finally:
        try:
            con.close()
        except Exception:
            pass

    logger.info(f"Daily cache build complete: {stats}")
    return stats


def get_all_available_symbols() -> list:
    """Retrieves all available symbols from Zerodha minute directory."""
    if os.path.exists(ZERODHA_MINUTE_DIR):
        try:
            files = os.listdir(ZERODHA_MINUTE_DIR)
            syms = [f[:-8] for f in files if f.endswith('.parquet')]
            if syms:
                return sorted(syms)
        except Exception as e:
            logger.error(f"Error listing Zerodha dir: {e}")
    return []


def get_symbols_for_segment(segment: str = 'nifty50') -> list:
    """Retrieves symbols for a given segment."""
    segment = segment.lower().strip()
    if segment == 'nifty50' and os.path.exists(NIFTY50_FILE):
        try:
            df = pd.read_csv(NIFTY50_FILE)
            col = 'Symbol' if 'Symbol' in df.columns else df.columns[0]
            return df[col].dropna().unique().tolist()
        except Exception:
            pass

    if segment == 'nifty500' and os.path.exists(NIFTY500_FILE):
        try:
            df = pd.read_csv(NIFTY500_FILE)
            col = 'Symbol' if 'Symbol' in df.columns else df.columns[2]
            return df[col].dropna().unique().tolist()
        except Exception:
            pass

    if segment in ['all', 'universe', 'parquet']:
        all_syms = get_all_available_symbols()
        if all_syms:
            return all_syms

    return ['TCS', 'INFY', 'RELIANCE', 'HDFCBANK', 'ICICIBANK']


def get_daily_cache_status() -> dict:
    """Returns status metrics for the adjusted daily cache."""
    available = get_all_available_symbols()
    cached = []
    if os.path.exists(ADJUSTED_DAILY_DIR):
        try:
            cached = [f[:-8] for f in os.listdir(ADJUSTED_DAILY_DIR) if f.endswith('.parquet')]
        except Exception:
            cached = []

    last_updated = "-"
    if cached:
        try:
            sample_file = os.path.join(ADJUSTED_DAILY_DIR, f"{cached[0]}.parquet")
            mtime = os.path.getmtime(sample_file)
            last_updated = datetime.fromtimestamp(mtime).strftime('%d-%b-%Y %H:%M')
        except Exception:
            pass

    return {
        "total_cached": len(cached),
        "total_available": len(available),
        "last_updated": last_updated,
        "is_ready": len(cached) > 0
    }


def main():
    parser = argparse.ArgumentParser(description="Build and Cache Pre-Adjusted Daily Parquet Files")
    parser.add_argument('--segment', type=str, default='nifty50', choices=['nifty50', 'nifty500', 'all', 'parquet'],
                        help="Stock universe to build daily cache for (default: nifty50)")
    parser.add_argument('--symbols', type=str, default=None,
                        help="Comma-separated symbols to build cache for (e.g. 'BAJAJFINSV,BEL,RELIANCE')")
    parser.add_argument('--force', action='store_true',
                        help="Force rebuild even if cache is already up-to-date")
    args = parser.parse_args()

    print("=" * 65)
    print("PRE-ADJUSTED DAILY PARQUET CACHE BUILDER")
    print("=" * 65)

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
        print(f"Targeting {len(symbols)} specified symbols: {symbols}")
    else:
        symbols = get_symbols_for_segment(args.segment)
        print(f"Targeting segment '{args.segment}' ({len(symbols)} symbols)")

    start_t = time.time()
    stats = build_daily_cache_batch(symbols, force=args.force)
    elapsed = round(time.time() - start_t, 2)

    print("=" * 65)
    print(f"Cache build completed in {elapsed}s.")
    print(f"Created: {stats['created']}, Updated: {stats['updated']}, Already Cached: {stats['cached']}, Skipped: {stats['skipped']}")
    print(f"Destination directory: {ADJUSTED_DAILY_DIR}")
    print("=" * 65)


if __name__ == '__main__':
    main()

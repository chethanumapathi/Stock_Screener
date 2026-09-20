"""
sync_minute_data.py
===================
Automated 1-Minute Historical Data Synchronizer via Kotak Neo API.
Synchronizes 1-minute historical candles from 2026-09-11 through 2026-09-18 (EOD)
and stitches them seamlessly into existing Parquet files in `C:\\Zerodha Historical Data\\data\\minute`.

Features:
- 100% token coverage (2,294 / 2,294 NSE stocks resolved).
- Intelligent gap detection: skips symbols already updated through 2026-09-18.
- Deduplication & chronological sorting via DuckDB atomic parquet stitching.
- Prioritized 3-Tier execution: Nifty 50 -> Nifty 500 -> All Remaining Stocks.
- Optional automatic rebuild of pre-adjusted daily cache (`build_daily_cache.py`).
"""

import os
import sys
import time
import json
import logging
import argparse
import duckdb
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import fetch_kotak_history as fkh

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("minute_sync")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ZERODHA_MINUTE_DIR = r"C:\Zerodha Historical Data\data\minute"
NIFTY50_FILE = os.path.join(DATA_DIR, 'nifty50.csv')
NIFTY500_FILE = os.path.join(DATA_DIR, 'nifty500.csv')


def get_prioritized_symbols(tier: str = 'all', specific_symbols: Optional[str] = None) -> List[str]:
    """Returns prioritized list of symbols: Nifty 50 -> Nifty 500 -> All remaining."""
    if specific_symbols:
        return [s.strip().upper().replace('.NS', '') for s in specific_symbols.split(',') if s.strip()]

    nifty50 = []
    if os.path.exists(NIFTY50_FILE):
        df50 = pd.read_csv(NIFTY50_FILE)
        nifty50 = [s.strip().upper() for s in df50['Symbol'].dropna().tolist()]

    nifty500 = []
    if os.path.exists(NIFTY500_FILE):
        df500 = pd.read_csv(NIFTY500_FILE)
        nifty500 = [s.strip().upper() for s in df500['Symbol'].dropna().tolist()]

    # All available parquet files
    all_files = [f for f in os.listdir(ZERODHA_MINUTE_DIR) if f.endswith('.parquet')]
    all_parquet_syms = sorted([os.path.splitext(f)[0].upper() for f in all_files])

    if tier == 'nifty50':
        return [s for s in nifty50 if s in all_parquet_syms]

    if tier == 'nifty500':
        ordered = []
        seen = set()
        for s in nifty50 + nifty500:
            if s in all_parquet_syms and s not in seen:
                ordered.append(s)
                seen.add(s)
        return ordered

    # Tier 'all': Nifty 50 first, then Nifty 500, then all remaining
    ordered = []
    seen = set()
    for s in nifty50:
        if s in all_parquet_syms and s not in seen:
            ordered.append(s)
            seen.add(s)
    for s in nifty500:
        if s in all_parquet_syms and s not in seen:
            ordered.append(s)
            seen.add(s)
    for s in all_parquet_syms:
        if s not in seen:
            ordered.append(s)
            seen.add(s)

    return ordered


def sync_minute_data(
    tier: str = 'all',
    symbols_str: Optional[str] = None,
    target_date: str = '2026-09-18',
    sleep_interval: float = 0.20,
    rebuild_daily: bool = True
):
    print("=" * 70)
    print(f" NSE 1-MINUTE HISTORICAL DATA SYNC (Through {target_date})")
    print("=" * 70)

    # 1. Load Kotak credentials & initialize client
    config = fkh.load_env_config("kotak_credentials.env")
    if not config.get("KOTAK_CONSUMER_KEY"):
        logger.error("No KOTAK_CONSUMER_KEY found in kotak_credentials.env!")
        sys.exit(1)

    logger.info("Connecting to Kotak Neo API...")
    client_mgr = fkh.KotakClientManager(config)
    scrip_resolver = fkh.ScripResolver(client_mgr)

    # 2. Get symbol list
    symbols = get_prioritized_symbols(tier=tier, specific_symbols=symbols_str)
    total = len(symbols)
    logger.info(f"Target scope: {total} symbols (Tier: {tier}). Target sync date: {target_date}")

    target_dt_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    # Fetch window end date (next day for full intraday session coverage)
    to_date_str = (target_dt_obj + timedelta(days=1)).strftime("%Y-%m-%d")

    # 3. Synchronize
    updated_symbols = []
    skipped_count = 0
    failed_count = 0
    start_time = time.time()

    for idx, sym in enumerate(symbols, 1):
        p_file = os.path.join(ZERODHA_MINUTE_DIR, f"{sym}.parquet")
        min_dt, max_dt, row_count = fkh.inspect_existing_file(p_file)

        # Check if already up to date
        if max_dt and max_dt.date() >= target_dt_obj:
            skipped_count += 1
            if idx % 100 == 0 or idx == total:
                logger.info(f"[{idx}/{total}] [{sym}] Up to date (max: {max_dt.strftime('%Y-%m-%d %H:%M')}). Skipped: {skipped_count}")
            continue

        # Determine start date
        if max_dt:
            # If max_dt is on or before 2026-09-11, start from 2026-09-12
            if max_dt.date() <= datetime(2026, 9, 11).date():
                from_date_str = "2026-09-12"
            else:
                from_date_str = (max_dt.date() + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            from_date_str = "2026-09-11"

        neo_token = scrip_resolver.get_token(sym)
        if not neo_token:
            logger.warning(f"[{idx}/{total}] [{sym}] Token not found in Kotak scrip master. Skipping.")
            failed_count += 1
            continue

        time.sleep(sleep_interval)
        try:
            res = client_mgr.fetch_historical_candles(
                neo_symbol=neo_token,
                interval="1min",
                from_date=from_date_str,
                to_date=to_date_str
            )
            df_chunk = fkh.parse_candles_to_df(res)

            if not df_chunk.empty:
                ok, total_rows, msg = fkh.stitch_and_save_parquet(p_file, df_chunk)
                if ok:
                    new_min, new_max, _ = fkh.inspect_existing_file(p_file)
                    new_max_str = new_max.strftime('%Y-%m-%d %H:%M') if new_max else '-'
                    logger.info(
                        f"[{idx}/{total}] ({idx/total*100:.1f}%) [{sym}] Stitched {len(df_chunk)} candles -> "
                        f"New Max: {new_max_str} (Total: {total_rows:,} rows)"
                    )
                    updated_symbols.append(sym)
                else:
                    logger.error(f"[{idx}/{total}] [{sym}] Stitch failed: {msg}")
                    failed_count += 1
            else:
                # No new trading candles (e.g. suspended / illiquid stock)
                logger.debug(f"[{idx}/{total}] [{sym}] No candles returned between {from_date_str} and {to_date_str}.")
                skipped_count += 1
        except Exception as e:
            logger.error(f"[{idx}/{total}] [{sym}] Error syncing: {e}")
            failed_count += 1

        # Periodic status summary every 100 stocks
        if idx % 100 == 0:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 0
            eta_mins = (total - idx) / rate / 60 if rate > 0 else 0
            logger.info(f"--- Progress: {idx}/{total} ({idx/total*100:.1f}%) | Updated: {len(updated_symbols)} | Skipped: {skipped_count} | ETA: {eta_mins:.1f}m ---")

    elapsed_total = time.time() - start_time
    print("=" * 70)
    print(f" 1-MINUTE SYNC COMPLETE in {elapsed_total/60:.2f} minutes!")
    print(f" Total Processed: {total} | Updated: {len(updated_symbols)} | Skipped: {skipped_count} | Failed: {failed_count}")
    print("=" * 70)

    # 4. Rebuild daily cache if requested
    if rebuild_daily and updated_symbols:
        logger.info(f"Triggering pre-adjusted daily cache rebuild for {len(updated_symbols)} updated stocks...")
        try:
            import build_daily_cache as bdc
            splits_cache = bdc.load_splits_cache()
            shared_con = duckdb.connect()
            for sym in updated_symbols:
                bdc.build_single_stock_daily_cache(sym, force=True, con=shared_con, splits_cache=splits_cache)
            shared_con.close()
            logger.info("Pre-adjusted daily cache rebuild complete!")
        except Exception as e:
            logger.error(f"Error rebuilding daily cache: {e}")


def main():
    parser = argparse.ArgumentParser(description="Synchronize 1-Minute Historical Data through 2026-09-18")
    parser.add_argument("--tier", type=str, default="all", choices=["nifty50", "nifty500", "all"],
                        help="Scope: 'nifty50', 'nifty500', or 'all' (default: 'all')")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Specific comma-separated symbols (e.g. 'RELIANCE,TCS,INFY')")
    parser.add_argument("--target-date", type=str, default="2026-09-18",
                        help="Target sync date (YYYY-MM-DD, default: 2026-09-18)")
    parser.add_argument("--sleep", type=float, default=0.20,
                        help="Sleep between API calls (default: 0.20s)")
    parser.add_argument("--no-daily-cache", action="store_true",
                        help="Skip rebuilding daily cache")
    args = parser.parse_args()

    sync_minute_data(
        tier=args.tier,
        symbols_str=args.symbols,
        target_date=args.target_date,
        sleep_interval=args.sleep,
        rebuild_daily=not args.no_daily_cache
    )


if __name__ == "__main__":
    main()

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
from tqdm import tqdm

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from auth import KiteAuthManager
from instruments import load_nifty500_instruments, load_all_equities_instruments
from downloader import HistoricalDownloader


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Download historical data for all NSE listed equities using Zerodha Kite Connect."
    )
    parser.add_argument(
        "--source",
        type=str,
        default=config.DEFAULT_SOURCE,
        choices=["all_equities", "nifty500"],
        help="Universe source: 'all_equities' (downloads all ~2,294 actively listed NSE stocks) or 'nifty500' (default: all_equities)",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default=config.DEFAULT_INTERVAL,
        choices=list(config.MAX_CHUNK_DAYS.keys()),
        help=f"Candle timeframe/interval (default: {config.DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=config.DEFAULT_MONTHS,
        help=f"Number of past months to download (default: {config.DEFAULT_MONTHS})",
    )
    parser.add_argument(
        "--from-date",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format (overrides --months)",
    )
    parser.add_argument(
        "--to-date",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default=config.DEFAULT_FORMAT,
        choices=["csv", "parquet", "both"],
        help=f"Output file format (default: {config.DEFAULT_FORMAT})",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated list of specific symbols to download (e.g. RELIANCE,TCS,INFY)",
    )
    parser.add_argument(
        "--max-stocks",
        type=int,
        default=None,
        help="Limit download to the first N stocks (useful for quick testing)",
    )
    parser.add_argument(
        "--force-instruments",
        action="store_true",
        help="Force refresh the constituent instrument mapping from NSE and Zerodha",
    )
    parser.add_argument(
        "--force-redownload",
        action="store_true",
        help="Force full re-download even if data files already exist locally",
    )
    parser.add_argument(
        "--force-relogin",
        action="store_true",
        help="Force a new login even if a cached access token exists",
    )
    parser.add_argument(
        "--request-token",
        type=str,
        default=None,
        help="Zerodha Kite Connect request_token or full redirected URL for fresh login",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    print("\n" + "=" * 75)
    print("      ZERODHA KITE CONNECT - NSE ALL EQUITIES HISTORICAL DOWNLOADER")
    print("=" * 75)

    # 1. Validate API Credentials
    if not config.KITE_API_KEY or not config.KITE_API_SECRET:
        print("\n[ERROR] Missing Zerodha Kite API credentials!")
        print("Please configure KITE_API_KEY and KITE_API_SECRET in your .env file.\n")
        sys.exit(1)

    # 2. Date Range Computation
    try:
        from_date, to_date = config.get_date_range(
            months=args.months,
            from_date_str=args.from_date,
            to_date_str=args.to_date,
        )
    except Exception as e:
        print(f"\n[ERROR] Invalid date range: {e}")
        sys.exit(1)

    # 3. Authenticate with Zerodha
    try:
        auth_mgr = KiteAuthManager()
        if args.request_token:
            kite = auth_mgr.login_with_token(args.request_token)
        else:
            kite = auth_mgr.get_kite_session(force_relogin=args.force_relogin)
    except Exception as e:
        print(f"\n[ERROR] Failed to authenticate with Zerodha: {e}")
        sys.exit(1)

    # 4. Load Stock Universe
    try:
        if args.source == "all_equities":
            print("\nFetching official 'NSE All Equities' master file (EQUITY_L.csv) from NSE...")
            instruments_df = load_all_equities_instruments(
                kite=kite,
                force_refresh=args.force_instruments,
            )
        else:
            print("\nLoading Nifty 500 constituents...")
            instruments_df = load_nifty500_instruments(
                kite=kite,
                force_refresh=args.force_instruments,
            )
    except Exception as e:
        print(f"\n[ERROR] Failed to load stock universe: {e}")
        sys.exit(1)

    # Filter symbols if specified
    if args.symbols:
        selected_symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        instruments_df = instruments_df[instruments_df["tradingsymbol"].isin(selected_symbols)]
        if instruments_df.empty:
            print(f"\n[ERROR] None of the specified symbols ({selected_symbols}) matched the universe.")
            sys.exit(1)

    if args.max_stocks:
        instruments_df = instruments_df.head(args.max_stocks)

    total_stocks = len(instruments_df)

    # Check existing files
    interval_dir = config.DATA_DIR / args.interval
    interval_dir.mkdir(parents=True, exist_ok=True)
    existing_symbols = {p.stem.upper() for ext in ("*.parquet", "*.csv") for p in interval_dir.glob(ext)}
    existing_count = sum(1 for s in instruments_df["tradingsymbol"] if s in existing_symbols)

    # 5. Display Run Parameters
    chunk_days = config.MAX_CHUNK_DAYS.get(args.interval, 60)
    total_days = (to_date - from_date).days
    approx_chunks_per_stock = max(1, (total_days + chunk_days - 1) // chunk_days)
    approx_total_api_calls = total_stocks * approx_chunks_per_stock
    approx_est_seconds = approx_total_api_calls * config.RATE_LIMIT_DELAY

    print(f"\nRun Configuration:")
    print(f"  • Source          : {args.source.upper()} ({'NSE All Equities Master (EQUITY_L.csv)' if args.source == 'all_equities' else 'Nifty 500 Index'})")
    print(f"  • Interval        : {args.interval} (1-minute bars)")
    print(f"  • Date Range      : {from_date} to {to_date} ({total_days} calendar days, ~{args.months} months)")
    print(f"  • Max Chunk Window: {chunk_days} days per API request (~{approx_chunks_per_stock} chunks/stock)")
    print(f"  • Total Universe  : {total_stocks} stocks")
    print(f"  • Existing Files  : {existing_count} stocks (will be incrementally updated/backfilled)")
    print(f"  • Output Format   : {args.format.upper()}")
    print(f"  • Output Directory: {interval_dir}")
    print("-" * 75 + "\n")

    # 6. Start Download Process
    downloader = HistoricalDownloader(kite=kite, data_dir=config.DATA_DIR)
    start_time = time.time()

    stats = {
        "success": 0,
        "skipped": 0,
        "no_data": 0,
        "failed": 0,
        "total_rows": 0,
    }
    failed_symbols = []

    pbar = tqdm(
        instruments_df.itertuples(),
        total=total_stocks,
        desc="Overall Progress",
        unit="stock",
        dynamic_ncols=True,
    )

    for row in pbar:
        symbol = row.tradingsymbol
        token = int(row.instrument_token)

        listing_date = None
        if hasattr(row, "listing_date") and pd.notna(row.listing_date):
            try:
                listing_date = pd.to_datetime(row.listing_date).date()
            except Exception:
                listing_date = None

        pbar.set_postfix({"current": symbol, "ok": stats["success"], "skip": stats["skipped"]})

        try:
            res = downloader.download_symbol(
                symbol=symbol,
                instrument_token=token,
                from_date=from_date,
                to_date=to_date,
                interval=args.interval,
                export_format=args.format,
                force_redownload=args.force_redownload,
                listing_date=listing_date,
            )

            status = res["status"]
            if status == "SUCCESS":
                stats["success"] += 1
                stats["total_rows"] += res.get("rows_added", 0)
            elif status == "SKIPPED":
                stats["skipped"] += 1
            elif status == "NO_DATA":
                stats["no_data"] += 1

        except Exception as e:
            err_str = str(e).lower()
            if "access_token" in err_str or "tokenexception" in type(e).__name__.lower():
                tqdm.write(f"\n[FATAL] Kite session expired while downloading {symbol}: {e}")
                tqdm.write("Zerodha tokens expire daily at 06:00 AM IST. Please generate a new request_token to resume.\n")
                sys.exit(1)

            stats["failed"] += 1
            failed_symbols.append((symbol, str(e)))
            tqdm.write(f"[ERROR] {symbol}: {e}")

    elapsed = time.time() - start_time

    # 7. Summary Report
    print("\n" + "=" * 75)
    print("                     DOWNLOAD SUMMARY REPORT")
    print("=" * 75)
    print(f"  Total Stocks Attempted : {total_stocks}")
    print(f"  Successfully Downloaded: {stats['success']}")
    print(f"  Already Up to Date     : {stats['skipped']}")
    print(f"  No Data Returned       : {stats['no_data']}")
    print(f"  Failed Stocks          : {stats['failed']}")
    print(f"  Total Candle Rows Saved: {stats['total_rows']:,}")
    print(f"  Time Elapsed           : {elapsed / 60:.2f} minutes")
    print(f"  Saved Files Directory  : {config.DATA_DIR / args.interval}")
    print("=" * 75)

    if failed_symbols:
        print("\nFailed Symbols:")
        for s, err in failed_symbols:
            print(f"  - {s}: {err}")
        print("\nYou can retry failed symbols with: python main.py --symbols " + ",".join([s for s, _ in failed_symbols]))

    print("\nAll done!")


if __name__ == "__main__":
    main()

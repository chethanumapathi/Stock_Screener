import argparse
import sys
import time
from datetime import date, datetime
from pathlib import Path
import pandas as pd
from tqdm import tqdm

import config
from auth import KiteAuthManager
from downloader import HistoricalDownloader

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Targeted updater: downloads missing afternoon candles (up to 3:30 PM) for all symbols that stopped mid-session."
    )
    parser.add_argument(
        "--request-token",
        type=str,
        default=None,
        help="Zerodha Kite Connect request_token or full redirected URL for fresh login.",
    )
    parser.add_argument(
        "--date",
        type=str,
        default="2026-09-11",
        help="Date to update (default: 2026-09-11).",
    )
    parser.add_argument(
        "--max-stocks",
        type=int,
        default=None,
        help="Limit update to first N stocks (useful for testing).",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated list of specific symbols to update.",
    )
    return parser.parse_args()


def find_incomplete_files(data_dir: Path, target_date: date) -> list[tuple[str, Path, datetime]]:
    """
    Scans parquet files and returns list of (symbol, path, max_timestamp)
    for files whose latest candle on target_date is before 15:25:00.
    """
    parquet_files = sorted(list(data_dir.glob("*.parquet")))
    incomplete = []

    print(f"Scanning {len(parquet_files)} parquet files in {data_dir}...")
    for p in tqdm(parquet_files, desc="Scanning files", unit="file", dynamic_ncols=True):
        try:
            df = pd.read_parquet(p, columns=["date"])
            if df.empty:
                incomplete.append((p.stem.upper(), p, None))
                continue
            max_dt = df["date"].max()
            if max_dt.date() == target_date and max_dt.time() < datetime.strptime("15:25:00", "%H:%M:%S").time():
                incomplete.append((p.stem.upper(), p, max_dt))
            elif max_dt.date() < target_date:
                incomplete.append((p.stem.upper(), p, max_dt))
        except Exception as e:
            print(f"Warning reading {p.name}: {e}")

    return incomplete


def main():
    args = parse_arguments()
    target_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    print("\n" + "=" * 75)
    print("       ZERODHA HISTORICAL DATA - AFTERNOON CANDLE UPDATER (UNTIL 3:30 PM)")
    print("=" * 75)

    # 1. Authenticate with Kite Connect
    auth_mgr = KiteAuthManager()
    if args.request_token:
        print(f"\nAuthenticating with provided request token...")
        kite = auth_mgr.login_with_token(args.request_token)
    else:
        kite = auth_mgr.get_kite_session()

    # 2. Load instrument token mapping
    inst_cache = config.DATA_DIR / "instruments" / "nse_all_equities.csv"
    if not inst_cache.exists():
        print(f"[ERROR] Instrument cache not found at {inst_cache}!")
        sys.exit(1)

    inst_df = pd.read_csv(inst_cache)
    token_map = dict(zip(inst_df["tradingsymbol"].str.upper(), inst_df["instrument_token"].astype(int)))

    # 3. Find files needing update
    data_dir = config.DATA_DIR / "minute"
    incomplete = find_incomplete_files(data_dir, target_date)

    if args.symbols:
        filter_syms = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
        incomplete = [item for item in incomplete if item[0] in filter_syms]

    if args.max_stocks:
        incomplete = incomplete[:args.max_stocks]

    total_to_update = len(incomplete)
    print(f"\nFound {total_to_update} stocks needing update for {target_date} (cut off before 3:30 PM).")
    if total_to_update == 0:
        print("All stocks are already up to date through 3:30 PM! Nothing to do.")
        return

    est_minutes = (total_to_update * config.RATE_LIMIT_DELAY) / 60
    print(f"Estimated download duration: ~{est_minutes:.1f} minutes (throttled at {config.RATE_LIMIT_DELAY}s/req).")
    print("-" * 75 + "\n")

    downloader = HistoricalDownloader(kite=kite, data_dir=config.DATA_DIR)
    success_count = 0
    total_new_rows = 0
    failed = []

    pbar = tqdm(incomplete, total=total_to_update, desc="Updating to 3:30 PM", unit="stock", dynamic_ncols=True)
    for symbol, path, last_dt in pbar:
        token = token_map.get(symbol)
        if not token:
            tqdm.write(f"Skipping {symbol}: instrument token not found.")
            continue

        pbar.set_postfix({"curr": symbol, "ok": success_count, "new_rows": total_new_rows})

        try:
            res = downloader.download_symbol(
                symbol=symbol,
                instrument_token=token,
                from_date=target_date,
                to_date=target_date,
                interval="minute",
                export_format="parquet",
                force_redownload=False,
            )

            if res["status"] == "SUCCESS":
                success_count += 1
                total_new_rows += res.get("rows_added", 0)
        except Exception as e:
            failed.append((symbol, str(e)))
            tqdm.write(f"[ERROR] {symbol}: {e}")

    print("\n" + "=" * 75)
    print("                         UPDATE SUMMARY REPORT")
    print("=" * 75)
    print(f"  Target Date               : {target_date}")
    print(f"  Total Attempted           : {total_to_update}")
    print(f"  Successfully Updated      : {success_count}")
    print(f"  Failed Stocks             : {len(failed)}")
    print(f"  New Afternoon Candles Added: {total_new_rows:,}")
    print("=" * 75)

    if failed:
        print(f"\nFailed Symbols ({len(failed)}):")
        for sym, err in failed[:10]:
            print(f"  - {sym}: {err}")


if __name__ == "__main__":
    main()

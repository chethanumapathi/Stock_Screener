import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Tuple

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pyarrow.csv as pv
import pyarrow.parquet as pq
from tqdm import tqdm

import config


def convert_file(csv_path: Path, parquet_path: Path, compression: str = "snappy") -> Tuple[bool, int, int, str]:
    """
    Convert a single CSV file to Parquet using PyArrow.
    Returns (success, original_size, parquet_size, error_msg).
    """
    try:
        orig_size = csv_path.stat().st_size
        table = pv.read_csv(csv_path)
        pq.write_table(table, parquet_path, compression=compression)
        pq_size = parquet_path.stat().st_size
        return True, orig_size, pq_size, ""
    except Exception as e:
        return False, 0, 0, str(e)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Fast multi-threaded CSV to Parquet converter for Zerodha historical candle data."
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="minute",
        help="Subdirectory interval to convert (default: minute)",
    )
    parser.add_argument(
        "--compression",
        type=str,
        default="snappy",
        choices=["snappy", "zstd", "gzip", "none"],
        help="Parquet compression codec (default: snappy)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, (os.cpu_count() or 4)),
        help="Number of concurrent conversion threads (default: 8)",
    )
    parser.add_argument(
        "--delete-csv",
        action="store_true",
        help="Delete original CSV files after successful conversion (default: False)",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    data_dir = config.DATA_DIR / args.interval

    if not data_dir.exists():
        print(f"[ERROR] Directory not found: {data_dir}")
        sys.exit(1)

    csv_files = sorted(list(data_dir.glob("*.csv")))
    total_files = len(csv_files)

    if total_files == 0:
        print(f"[INFO] No CSV files found in {data_dir}.")
        sys.exit(0)

    print("\n" + "=" * 75)
    print("           HISTORICAL DATA: CSV TO PARQUET BATCH CONVERTER")
    print("=" * 75)
    print(f"  • Source Directory : {data_dir}")
    print(f"  • Total CSV Files  : {total_files:,}")
    print(f"  • Compression      : {args.compression.upper()}")
    print(f"  • Parallel Workers : {args.workers}")
    print(f"  • Delete CSVs      : {'YES' if args.delete_csv else 'NO (keeping both)'}")
    print("-" * 75 + "\n")

    start_time = time.time()
    total_orig_bytes = 0
    total_pq_bytes = 0
    success_count = 0
    failed_count = 0
    failed_files = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_csv = {
            executor.submit(
                convert_file,
                csv_file,
                data_dir / f"{csv_file.stem}.parquet",
                args.compression,
            ): csv_file
            for csv_file in csv_files
        }

        pbar = tqdm(
            as_completed(future_to_csv),
            total=total_files,
            desc="Converting to Parquet",
            unit="file",
            dynamic_ncols=True,
        )

        for future in pbar:
            csv_file = future_to_csv[future]
            try:
                ok, orig_sz, pq_sz, err = future.result()
                if ok:
                    success_count += 1
                    total_orig_bytes += orig_sz
                    total_pq_bytes += pq_sz
                    if args.delete_csv:
                        try:
                            csv_file.unlink()
                        except Exception:
                            pass
                else:
                    failed_count += 1
                    failed_files.append((csv_file.name, err))
            except Exception as e:
                failed_count += 1
                failed_files.append((csv_file.name, str(e)))

    elapsed = time.time() - start_time
    orig_gb = total_orig_bytes / (1024 ** 3)
    pq_gb = total_pq_bytes / (1024 ** 3)
    saved_gb = orig_gb - pq_gb
    pct_saved = (saved_gb / orig_gb * 100) if orig_gb > 0 else 0

    print("\n" + "=" * 75)
    print("                         CONVERSION SUMMARY")
    print("=" * 75)
    print(f"  Total Files Processed   : {total_files:,}")
    print(f"  Successfully Converted  : {success_count:,}")
    print(f"  Failed Conversions      : {failed_count}")
    print(f"  Original CSV Total Size : {orig_gb:.2f} GB")
    print(f"  New Parquet Total Size  : {pq_gb:.2f} GB")
    print(f"  Storage Space Saved     : {saved_gb:.2f} GB ({pct_saved:.1f}% reduction)")
    print(f"  Time Elapsed            : {elapsed:.2f} seconds (~{total_files/elapsed:.1f} files/sec)")
    print(f"  Parquet Output Directory: {data_dir}")
    print("=" * 75 + "\n")

    if failed_files:
        print("Failed Files:")
        for name, err in failed_files:
            print(f"  - {name}: {err}")


if __name__ == "__main__":
    main()

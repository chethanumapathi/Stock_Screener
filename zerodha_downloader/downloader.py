import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from kiteconnect import KiteConnect
from kiteconnect.exceptions import NetworkException, DataException

import config

logger = logging.getLogger(__name__)


class HistoricalDownloader:
    """
    Downloads historical candle data from Zerodha Kite Connect with:
    - Smart date chunking (e.g., 60-day windows for 1-minute data)
    - Rate limit throttling (safe 0.38s pacing, well within Kite's 3 req/sec limit)
    - Exponential backoff retry on network issues or rate limits
    - Automatic resume & incremental appending for interrupted downloads
    - Multi-format support (CSV, Parquet, or both)
    """

    def __init__(self, kite: KiteConnect, data_dir: Path = None):
        self.kite = kite
        self.data_dir = data_dir or config.DATA_DIR

    @staticmethod
    def generate_chunks(from_date: date, to_date: date, max_chunk_days: int) -> List[Tuple[date, date]]:
        """
        Split a date range [from_date, to_date] into chunks of at most max_chunk_days.
        """
        chunks = []
        curr_start = from_date
        while curr_start <= to_date:
            curr_end = min(curr_start + timedelta(days=max_chunk_days - 1), to_date)
            chunks.append((curr_start, curr_end))
            curr_start = curr_end + timedelta(days=1)
        return chunks

    def _fetch_chunk_with_retry(
        self,
        instrument_token: int,
        from_date: date,
        to_date: date,
        interval: str,
        max_retries: int = 4,
    ) -> List[dict]:
        """
        Calls kite.historical_data with throttling and exponential backoff retry.
        """
        retries = 0
        backoff = 2.0

        while retries <= max_retries:
            try:
                # Respect rate limits (max 3 req/sec on Kite)
                time.sleep(config.RATE_LIMIT_DELAY)

                records = self.kite.historical_data(
                    instrument_token=instrument_token,
                    from_date=from_date,
                    to_date=to_date,
                    interval=interval,
                    continuous=False,
                    oi=False,
                )
                return records or []

            except Exception as e:
                error_msg = str(e).lower()

                # If token has expired or is invalid, fail fast immediately
                if "access_token" in error_msg or "tokenexception" in type(e).__name__.lower():
                    logger.error(f"Kite session expired for token {instrument_token}: {e}")
                    raise

                retries += 1

                if "429" in error_msg or "too many requests" in error_msg:
                    sleep_time = backoff * 2
                    logger.warning(
                        f"Rate limit 429 hit for token {instrument_token}. "
                        f"Backing off for {sleep_time:.1f}s (retry {retries}/{max_retries})."
                    )
                    time.sleep(sleep_time)
                elif retries <= max_retries:
                    logger.warning(
                        f"API request failed for token {instrument_token} ({e}). "
                        f"Retrying in {backoff:.1f}s (retry {retries}/{max_retries})..."
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        f"Max retries reached for token {instrument_token} "
                        f"chunk {from_date} to {to_date}: {e}"
                    )
                    raise

                backoff *= 1.5

        return []

    def _get_output_paths(self, symbol: str, interval: str) -> Dict[str, Path]:
        """Generate output paths for CSV and Parquet formats."""
        interval_dir = self.data_dir / interval
        interval_dir.mkdir(parents=True, exist_ok=True)
        return {
            "csv": interval_dir / f"{symbol}.csv",
            "parquet": interval_dir / f"{symbol}.parquet",
        }

    def _load_existing_data(self, symbol: str, interval: str, file_format: str) -> Optional[pd.DataFrame]:
        """Load existing data if available for incremental sync."""
        paths = self._get_output_paths(symbol, interval)
        target_path = paths.get(file_format, paths["csv"])

        # Check primary format or fallback format
        if not target_path.exists():
            fallback = paths["parquet"] if file_format == "csv" else paths["csv"]
            if fallback.exists():
                target_path = fallback
            else:
                return None

        try:
            if target_path.suffix == ".parquet":
                df = pd.read_parquet(target_path)
            else:
                df = pd.read_csv(target_path)

            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                if df["date"].dt.tz is not None:
                    df["date"] = df["date"].dt.tz_localize(None)
                return df
        except Exception as e:
            logger.warning(f"Could not read existing file for {symbol} ({e}). Will re-download.")

        return None

    def _save_data(self, df: pd.DataFrame, symbol: str, interval: str, export_format: str):
        """Save DataFrame to CSV, Parquet, or both."""
        paths = self._get_output_paths(symbol, interval)

        # Ensure sorted and deduplicated by date
        df = df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)

        # Standardize date column format in string for CSV
        if export_format in ("csv", "both"):
            df_csv = df.copy()
            df_csv["date"] = df_csv["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
            df_csv.to_csv(paths["csv"], index=False)

        if export_format in ("parquet", "both"):
            df.to_parquet(paths["parquet"], index=False, engine="pyarrow")

    def download_symbol(
        self,
        symbol: str,
        instrument_token: int,
        from_date: date,
        to_date: date,
        interval: str = "minute",
        export_format: str = "csv",
        force_redownload: bool = False,
        listing_date: Optional[date] = None,
    ) -> Dict:
        """
        Download historical data for a single symbol across chunks.
        Performs incremental resume if data already exists.
        """
        # Clamp start date to stock's actual listing/IPO date if available
        if listing_date and isinstance(listing_date, date):
            from_date = max(from_date, listing_date)

        max_chunk = config.MAX_CHUNK_DAYS.get(interval, 60)
        existing_df = None

        if not force_redownload:
            existing_df = self._load_existing_data(symbol, interval, export_format)

        if from_date > to_date:
            return {
                "symbol": symbol,
                "status": "SKIPPED",
                "rows_added": 0,
                "total_rows": len(existing_df) if existing_df is not None else 0,
                "message": f"Listing date ({listing_date}) is after to_date ({to_date})",
            }

        needed_ranges: List[Tuple[date, date]] = []

        if existing_df is not None and not existing_df.empty:
            min_existing = existing_df["date"].min().date()
            max_existing_dt = existing_df["date"].max()
            max_existing = max_existing_dt.date()

            # For intraday intervals, verify whether the latest day reached market close (~15:25+ IST)
            is_intraday = interval != "day"
            is_last_day_complete = True
            if is_intraday:
                is_last_day_complete = max_existing_dt.time() >= datetime.strptime("15:25:00", "%H:%M:%S").time()

            # Check if start is already covered (or within 5 days of listing due to weekend/holiday)
            is_start_covered = min_existing <= from_date or (listing_date is not None and min_existing <= listing_date + timedelta(days=5))

            # If existing data already covers the requested range completely
            if is_start_covered and max_existing >= to_date and is_last_day_complete:
                return {
                    "symbol": symbol,
                    "status": "SKIPPED",
                    "rows_added": 0,
                    "total_rows": len(existing_df),
                    "message": f"Already complete ({min_existing} to {max_existing})",
                }

            # Fetch earlier missing data if requested range starts earlier
            if from_date < min_existing and not (listing_date is not None and min_existing <= listing_date + timedelta(days=5)):
                needed_ranges.append((from_date, min_existing - timedelta(days=1)))

            # Fetch newer missing data if requested range ends later or if latest date is incomplete
            if to_date > max_existing:
                start_fetch = max_existing if not is_last_day_complete else (max_existing + timedelta(days=1))
                needed_ranges.append((start_fetch, to_date))
            elif not is_last_day_complete:
                # Same day or covered date range, but latest intraday data was cut off mid-session
                needed_ranges.append((max_existing, max_existing))
        else:
            needed_ranges.append((from_date, to_date))

        new_records = []
        for r_start, r_end in needed_ranges:
            if r_start > r_end:
                continue

            chunks = self.generate_chunks(r_start, r_end, max_chunk)
            for c_start, c_end in chunks:
                chunk_records = self._fetch_chunk_with_retry(
                    instrument_token=instrument_token,
                    from_date=c_start,
                    to_date=c_end,
                    interval=interval,
                )
                if chunk_records:
                    new_records.extend(chunk_records)

        # Process and combine
        if not new_records:
            if existing_df is not None and not existing_df.empty:
                return {
                    "symbol": symbol,
                    "status": "SKIPPED",
                    "rows_added": 0,
                    "total_rows": len(existing_df),
                    "message": "Already up to date (no new records)",
                }
            return {
                "symbol": symbol,
                "status": "NO_DATA",
                "rows_added": 0,
                "total_rows": 0,
                "message": "No records returned by Kite API",
            }

        new_df = pd.DataFrame(new_records)
        if not new_df.empty and "date" in new_df.columns:
            new_df["date"] = pd.to_datetime(new_df["date"])
            if new_df["date"].dt.tz is not None:
                new_df["date"] = new_df["date"].dt.tz_localize(None)

        existing_count = len(existing_df) if existing_df is not None else 0
        if existing_df is not None and not existing_df.empty:
            if not new_df.empty:
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                combined_df = existing_df
        else:
            combined_df = new_df

        # Count deduplicated rows
        dedup_total = len(combined_df.drop_duplicates(subset=["date"]))
        rows_added = max(0, dedup_total - existing_count)

        if rows_added == 0 and existing_count > 0:
            return {
                "symbol": symbol,
                "status": "SKIPPED",
                "rows_added": 0,
                "total_rows": existing_count,
                "message": f"Already complete ({existing_count} records)",
            }

        self._save_data(combined_df, symbol, interval, export_format)

        return {
            "symbol": symbol,
            "status": "SUCCESS" if rows_added > 0 else "NO_DATA",
            "rows_added": rows_added,
            "total_rows": dedup_total,
            "message": f"Saved {dedup_total} records (+{rows_added} new)",
        }

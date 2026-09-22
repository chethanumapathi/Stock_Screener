"""
fetch_kotak_history.py
======================
Automated, resilient historical 1-minute data fetcher using Kotak Neo API.
Fetches missing historical chunks (e.g. 2021-09-01 to 2023-09-12) and stitches
them seamlessly into existing Parquet files in `C:\\Zerodha Historical Data\\data\\minute`.

Features:
- Instant gap detection (inspects min(date) in existing Parquet files via DuckDB).
- Slices missing date ranges into 30-day API chunks.
- Atomic Parquet writer (prevents corrupted files on interruption).
- Seamless deduplication and chronological ordering (date ASC).
- Priority ordering: Nifty 50 -> Nifty 500 -> All remaining 2,294+ NSE stocks.
- Resumable: can be stopped and restarted anytime without duplicate work.
"""

import os
import sys
import time
import json
import logging
import argparse
import requests
import duckdb
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Try loading pyotp for automated TOTP 2FA
try:
    import pyotp
except ImportError:
    pyotp = None

# Try importing official Kotak Neo SDK
try:
    from neo_api_client import NeoAPI
except ImportError:
    NeoAPI = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("kotak_fetcher")

# Default Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = r"C:\Zerodha Historical Data\data\minute"
FALLBACK_DATA_DIR = os.path.join(BASE_DIR, "data", "minute")
SCRIP_CACHE_FILE = os.path.join(BASE_DIR, "data", "kotak_scrip_master_nse_cm.csv")
NIFTY50_FILE = os.path.join(BASE_DIR, "data", "nifty50.csv")
NIFTY500_FILE = os.path.join(BASE_DIR, "data", "nifty500.csv")


def load_env_config(env_file_path: str = "kotak_credentials.env") -> Dict[str, str]:
    """Loads environment configuration from file."""
    config = {}
    search_paths = [
        env_file_path,
        os.path.join(BASE_DIR, env_file_path),
        os.path.join(BASE_DIR, "kotak_credentials.env"),
        os.path.join(BASE_DIR, ".env")
    ]
    
    found_file = None
    for p in search_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            found_file = p
            break
            
    if found_file:
        logger.info(f"Loading configuration from: {found_file}")
        with open(found_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip('"').strip("'")
    return config


class KotakClientManager:
    """Manages authentication and communication with Kotak Neo API."""

    def __init__(self, config: Dict[str, str]):
        if NeoAPI is None:
            raise RuntimeError("Kotak Neo SDK ('kotakneoapi') is not installed. Run: pip install pydantic kotakneoapi")

        self.consumer_key = config.get("KOTAK_CONSUMER_KEY") or os.getenv("KOTAK_CONSUMER_KEY")
        self.consumer_secret = config.get("KOTAK_CONSUMER_SECRET") or os.getenv("KOTAK_CONSUMER_SECRET")
        self.mobile = config.get("KOTAK_MOBILE_NUMBER") or os.getenv("KOTAK_MOBILE_NUMBER")
        self.ucc = config.get("KOTAK_UCC") or os.getenv("KOTAK_UCC")
        self.mpin = config.get("KOTAK_MPIN") or os.getenv("KOTAK_MPIN")
        self.totp_key = config.get("KOTAK_TOTP_KEY") or os.getenv("KOTAK_TOTP_KEY")

        if not self.consumer_key:
            raise ValueError("KOTAK_CONSUMER_KEY is required in kotak_credentials.env")

        self.client = NeoAPI(
            consumer_key=self.consumer_key,
            environment="prod"
        )
        # Suppress neo_api_client file handler to avoid Windows [WinError 32] log-rotation lock conflicts
        neo_log = logging.getLogger("neo_api_client")
        for h in list(neo_log.handlers):
            if isinstance(h, logging.FileHandler):
                try:
                    h.close()
                    neo_log.removeHandler(h)
                except Exception:
                    pass
        self.is_authenticated = False

    def authenticate(self) -> bool:
        """Executes TOTP + MPIN 2FA login flow if login credentials are provided."""
        if not (self.mobile and self.ucc and self.mpin):
            logger.info("Mobile, UCC, or MPIN not fully supplied; proceeding with consumer_key authorization.")
            return True

        try:
            # Generate or prompt for TOTP
            if self.totp_key:
                if pyotp is None:
                    raise RuntimeError("pyotp is required for automated TOTP generation. Run: pip install pyotp")
                clean_totp_key = self.totp_key.replace(" ", "").strip()
                totp_val = pyotp.TOTP(clean_totp_key).now()
                logger.info(f"Generated auto-TOTP code for UCC: {self.ucc}")
            else:
                totp_val = input(f"Enter 6-digit TOTP from authenticator app for {self.ucc}: ").strip()

            # Step 1: TOTP Login
            login_res = self.client.totp_login(
                mobile_number=self.mobile,
                ucc=self.ucc,
                totp=totp_val
            )

            # Step 2: Validate MPIN
            val_res = self.client.totp_validate(mpin=self.mpin)

            logger.info(f"Successfully authenticated session for {self.ucc}.")
            self.is_authenticated = True
            return True
        except Exception as e:
            logger.warning(f"Login handshake notice: {e}. Historical Data API operates using consumer_key Authorization.")
            return False

    def get_scrip_master_csv_url(self) -> Optional[str]:
        """Retrieves the CSV download URL for the NSE Cash Market (nse_cm) instruments."""
        try:
            res = self.client.scrip_master(exchange_segment="nse_cm")
            if isinstance(res, str) and res.startswith("http"):
                return res
            elif isinstance(res, dict):
                # Check for filesPaths in dict response
                files = res.get("filesPaths", [])
                for f in files:
                    if "nse_cm" in f.lower():
                        return f
                if "data" in res and isinstance(res["data"], dict):
                    for f in res["data"].get("filesPaths", []):
                        if "nse_cm" in f.lower():
                            return f
            return None
        except Exception as e:
            logger.error(f"Error fetching scrip master URL: {e}")
            return None

    def fetch_historical_candles(
        self,
        neo_symbol: str,
        interval: str,
        from_date: str,
        to_date: str,
        max_retries: int = 3,
        backoff_delay: float = 2.0
    ) -> Optional[dict]:
        """
        Calls Kotak Neo historical data endpoint with retry and rate-limit backoff.
        """
        for attempt in range(1, max_retries + 1):
            try:
                res = self.client.historical_data(
                    neosymbol=neo_symbol,
                    interval=interval,
                    from_date=from_date,
                    to_date=to_date
                )
                # Check for error structures in response
                if isinstance(res, dict):
                    if "error" in res or "Error" in res:
                        err_msg = res.get("error") or res.get("Error")
                        status = res.get("StatusCode") or res.get("code")
                        if status in [429, 503, 504] or str(status) == "429":
                            logger.warning(f"Server returned {status} for {neo_symbol} ({from_date} to {to_date}). Retrying in {backoff_delay}s...")
                            time.sleep(backoff_delay)
                            backoff_delay *= 2
                            continue
                        logger.debug(f"Historical API note for {neo_symbol}: {err_msg}")
                        return res
                return res
            except Exception as ex:
                if attempt == max_retries:
                    logger.error(f"Failed to fetch {neo_symbol} after {max_retries} attempts: {ex}")
                    return None
                logger.warning(f"Attempt {attempt} failed for {neo_symbol}: {ex}. Backing off {backoff_delay}s...")
                time.sleep(backoff_delay)
                backoff_delay *= 2
        return None


class ScripResolver:
    """Downloads and caches Kotak Neo NSE equity instrument master mapping."""

    def __init__(self, client_mgr: KotakClientManager):
        self.client_mgr = client_mgr
        self.symbol_to_token: Dict[str, str] = {}
        self._load_or_download_master()

    def _load_or_download_master(self):
        """Loads master from local cache or downloads from Kotak API."""
        os.makedirs(os.path.dirname(SCRIP_CACHE_FILE), exist_ok=True)
        need_download = True

        if os.path.exists(SCRIP_CACHE_FILE) and os.path.getsize(SCRIP_CACHE_FILE) > 10000:
            file_age_hours = (time.time() - os.path.getmtime(SCRIP_CACHE_FILE)) / 3600
            if file_age_hours < 24:
                need_download = False
                logger.info(f"Loading cached Kotak scrip master ({file_age_hours:.1f}h old): {SCRIP_CACHE_FILE}")

        if need_download:
            logger.info("Requesting fresh Scrip Master file URL from Kotak Neo...")
            csv_url = self.client_mgr.get_scrip_master_csv_url()
            if csv_url:
                logger.info(f"Downloading Scrip Master CSV from: {csv_url}")
                try:
                    r = requests.get(csv_url, timeout=30)
                    if r.status_code == 200 and len(r.content) > 10000:
                        with open(SCRIP_CACHE_FILE, "wb") as f:
                            f.write(r.content)
                        logger.info(f"Saved scrip master to {SCRIP_CACHE_FILE} ({len(r.content)/1024:.1f} KB)")
                    else:
                        logger.warning(f"Failed to download scrip master CSV. Status: {r.status_code}")
                except Exception as e:
                    logger.error(f"Error downloading scrip master: {e}")
            else:
                logger.warning("Could not obtain scrip master CSV URL from API.")

        # Parse CSV if available
        if os.path.exists(SCRIP_CACHE_FILE) and os.path.getsize(SCRIP_CACHE_FILE) > 0:
            try:
                df = pd.read_csv(SCRIP_CACHE_FILE, low_memory=False)
                # Primary pass: Map standard Equity series (-EQ)
                eq_mask = df['pTrdSymbol'].str.endswith('-EQ', na=False)
                for _, row in df[eq_mask].iterrows():
                    tok = str(row['pSymbol']).strip()
                    sym_name = str(row['pSymbolName']).strip().upper()
                    clean_sym = sym_name.replace('.NS', '').strip()
                    if clean_sym and tok:
                        self.symbol_to_token[clean_sym] = f"nse_cm|{tok}"

                # Secondary pass: Map any remaining symbols (-BE, -SM, indices, etc.)
                for _, row in df[~eq_mask].iterrows():
                    tok = str(row['pSymbol']).strip()
                    sym_name = str(row['pSymbolName']).strip().upper()
                    clean_sym = sym_name.replace('.NS', '').strip()
                    if clean_sym and tok and clean_sym not in self.symbol_to_token:
                        self.symbol_to_token[clean_sym] = f"nse_cm|{tok}"

                logger.info(f"Resolved {len(self.symbol_to_token):,} NSE symbols in Kotak master lookup.")
            except Exception as e:
                logger.error(f"Error parsing scrip master CSV: {e}")

    def get_token(self, symbol: str) -> Optional[str]:
        """Returns the neo_symbol (e.g. 'nse_cm|2885') for a given trading symbol."""
        clean = symbol.upper().replace(".NS", "").strip()
        return self.symbol_to_token.get(clean)


def parse_candles_to_df(response: dict) -> pd.DataFrame:
    """
    Parses Kotak Neo historical response payload into a standardized DataFrame:
    Columns: date (datetime64[ns]), open, high, low, close, volume (all float64).
    """
    empty_df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    if not response or not isinstance(response, dict):
        return empty_df

    raw_candles = None
    data = response.get("data")
    if isinstance(data, list):
        raw_candles = data
    elif isinstance(data, dict):
        raw_candles = data.get("candles") or data.get("history") or data.get("data")
    elif "candles" in response:
        raw_candles = response["candles"]

    if not raw_candles or not isinstance(raw_candles, list):
        return empty_df

    rows = []
    for item in raw_candles:
        if isinstance(item, (list, tuple)) and len(item) >= 5:
            # Format: [timestamp, open, high, low, close, volume]
            dt_val = item[0]
            o = item[1]
            h = item[2]
            l = item[3]
            c = item[4]
            v = item[5] if len(item) > 5 else 0.0
            rows.append({"date": dt_val, "open": o, "high": h, "low": l, "close": c, "volume": v})
        elif isinstance(item, dict):
            # Normalize dictionary keys
            kmap = {str(k).lower(): v for k, v in item.items()}
            dt_val = kmap.get("date") or kmap.get("time") or kmap.get("timestamp") or kmap.get("t")
            o = kmap.get("open") or kmap.get("o")
            h = kmap.get("high") or kmap.get("h")
            l = kmap.get("low") or kmap.get("l")
            c = kmap.get("close") or kmap.get("c")
            v = kmap.get("volume") or kmap.get("v") or 0.0
            if dt_val is not None and o is not None:
                rows.append({"date": dt_val, "open": o, "high": h, "low": l, "close": c, "volume": v})

    if not rows:
        return empty_df

    df = pd.DataFrame(rows)
    # Parse date column safely
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    
    # Remove timezone offset if present to match local parquet naive timestamps
    if df["date"].dt.tz is not None:
        df["date"] = df["date"].dt.tz_localize(None)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    df = df.sort_values("date").reset_index(drop=True)
    return df


def inspect_existing_file(file_path: str) -> Tuple[Optional[datetime], Optional[datetime], int]:
    """
    Returns (min_date, max_date, row_count) for an existing Parquet file using DuckDB.
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return None, None, 0

    try:
        norm_path = file_path.replace("\\", "/")
        con = duckdb.connect()
        res = con.execute("SELECT min(date), max(date), count(*) FROM read_parquet(?)", [norm_path]).fetchone()
        con.close()
        if res and res[0] is not None:
            min_dt = pd.to_datetime(res[0]).to_pydatetime()
            max_dt = pd.to_datetime(res[1]).to_pydatetime()
            count = int(res[2])
            return min_dt, max_dt, count
    except Exception as e:
        logger.debug(f"DuckDB inspect error for {file_path}: {e}")
    return None, None, 0


def generate_date_chunks(start_dt: datetime, end_dt: datetime, chunk_days: int = 25) -> List[Tuple[str, str]]:
    """Generates contiguous (from_date, to_date) string tuples in chunk_days windows (<= 25 days)."""
    chunks = []
    curr = start_dt
    while curr <= end_dt:
        nxt = min(curr + timedelta(days=chunk_days - 1), end_dt)
        chunks.append((curr.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d")))
        curr = nxt + timedelta(days=1)
    return chunks


def stitch_and_save_parquet(existing_path: str, new_df: pd.DataFrame) -> Tuple[bool, int, str]:
    """
    Seamlessly merges newly fetched historical candles with existing Parquet data,
    deduplicates by timestamp, sorts chronologically, and writes atomically.
    """
    if new_df.empty:
        return False, 0, "No new data to stitch"

    norm_path = existing_path.replace("\\", "/")
    os.makedirs(os.path.dirname(existing_path), exist_ok=True)
    temp_path = existing_path + ".tmp"

    try:
        con = duckdb.connect()
        # Register new dataframe
        con.register("new_data", new_df)

        if os.path.exists(existing_path) and os.path.getsize(existing_path) > 0:
            # Query combining both sources, prioritizing existing or deduping by date
            sql = f"""
                CREATE TEMP TABLE merged AS
                SELECT 
                    CAST(date AS TIMESTAMP_NS) AS date,
                    CAST(open AS DOUBLE) AS open,
                    CAST(high AS DOUBLE) AS high,
                    CAST(low AS DOUBLE) AS low,
                    CAST(close AS DOUBLE) AS close,
                    CAST(volume AS DOUBLE) AS volume
                FROM (
                    SELECT * FROM read_parquet('{norm_path}')
                    UNION ALL
                    SELECT * FROM new_data
                )
                QUALIFY ROW_NUMBER() OVER (PARTITION BY date ORDER BY open) = 1
                ORDER BY date ASC
            """
            con.execute(sql)
        else:
            sql = """
                CREATE TEMP TABLE merged AS
                SELECT 
                    CAST(date AS TIMESTAMP_NS) AS date,
                    CAST(open AS DOUBLE) AS open,
                    CAST(high AS DOUBLE) AS high,
                    CAST(low AS DOUBLE) AS low,
                    CAST(close AS DOUBLE) AS close,
                    CAST(volume AS DOUBLE) AS volume
                FROM new_data
                ORDER BY date ASC
            """
            con.execute(sql)

        # Write to temporary parquet file
        norm_tmp = temp_path.replace("\\", "/")
        con.execute(f"COPY merged TO '{norm_tmp}' (FORMAT PARQUET, COMPRESSION SNAPPY)")
        row_count = con.execute("SELECT count(*) FROM merged").fetchone()[0]
        con.close()

        # Atomic replace
        if os.path.exists(existing_path):
            os.remove(existing_path)
        os.rename(temp_path, existing_path)

        return True, row_count, "OK"
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False, 0, str(e)


def get_prioritized_symbol_list(data_dir: str, scrip_resolver: ScripResolver, existing_only: bool = False) -> List[str]:
    """
    Returns ordered symbols:
    1. Nifty 50 stocks
    2. Nifty 500 stocks
    3. Existing stocks in data_dir (all 2,294 files)
    4. Any remaining NSE Equities from Scrip Master (if existing_only is False)
    """
    ordered_list = []
    seen = set()

    # Pre-compute set of existing symbols if existing_only is requested
    existing_symbols = set()
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith(".parquet") and not f.startswith("."):
                existing_symbols.add(f[:-8].upper())

    def add_symbols(syms, filter_existing=False):
        for s in syms:
            clean = s.upper().replace(".NS", "").strip()
            if clean and clean not in seen and scrip_resolver.get_token(clean):
                if filter_existing and existing_symbols and clean not in existing_symbols:
                    continue
                seen.add(clean)
                ordered_list.append(clean)

    # 1. Nifty 50
    if os.path.exists(NIFTY50_FILE):
        try:
            df50 = pd.read_csv(NIFTY50_FILE)
            col = [c for c in df50.columns if "symbol" in c.lower()][0]
            add_symbols(df50[col].dropna().tolist(), filter_existing=existing_only)
            logger.info(f"Loaded {len(ordered_list)} Nifty 50 symbols for Tier 1.")
        except Exception as e:
            logger.debug(f"Could not load Nifty 50: {e}")

    # 2. Nifty 500
    t1_count = len(ordered_list)
    if os.path.exists(NIFTY500_FILE):
        try:
            df500 = pd.read_csv(NIFTY500_FILE)
            col = [c for c in df500.columns if "symbol" in c.lower()][0]
            add_symbols(df500[col].dropna().tolist(), filter_existing=existing_only)
            logger.info(f"Loaded {len(ordered_list) - t1_count} additional Nifty 500 symbols for Tier 2.")
        except Exception as e:
            logger.debug(f"Could not load Nifty 500: {e}")

    # 3. Existing local Parquet files in data_dir
    t2_count = len(ordered_list)
    if existing_symbols:
        add_symbols(sorted(list(existing_symbols)))
        logger.info(f"Loaded {len(ordered_list) - t2_count} additional existing local symbols for Tier 3.")

    # 4. Remaining symbols in Scrip Master (if not existing_only)
    if not existing_only:
        t3_count = len(ordered_list)
        add_symbols(sorted(list(scrip_resolver.symbol_to_token.keys())))
        if len(ordered_list) > t3_count:
            logger.info(f"Loaded {len(ordered_list) - t3_count} additional NSE symbols from Kotak master for Tier 4.")

    return ordered_list


def main():
    parser = argparse.ArgumentParser(description="Resilient Kotak Neo 1-Minute Historical Data Downloader & Stitcher")
    parser.add_argument("--env", type=str, default="kotak_credentials.env", help="Path to credentials env file")
    parser.add_argument("--data-dir", type=str, default=None, help="Directory containing minute parquet files")
    parser.add_argument("--from-date", type=str, default="2021-09-01", help="Target start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=str, default="2023-09-12", help="Target end date (YYYY-MM-DD)")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols (e.g. RELIANCE,TCS)")
    parser.add_argument("--chunk-days", type=int, default=25, help="Days per API historical request (default: 25)")
    parser.add_argument("--sleep", type=float, default=0.35, help="Sleep interval between API calls (default: 0.35s)")
    parser.add_argument("--dry-run", action="store_true", help="Print gap inspection and scrip tokens without downloading")
    parser.add_argument("--force", action="store_true", help="Force download regardless of existing min(date)")
    parser.add_argument("--existing-only", action="store_true", help="Only process stocks already present in data directory (e.g. 2,294 stocks)")
    args = parser.parse_args()

    print("=" * 70)
    print(" KOTAK NEO 1-MINUTE HISTORICAL DATA SYNC PIPELINE ")
    print("=" * 70)

    # 1. Load config and determine storage directory
    config = load_env_config(args.env)
    data_dir = args.data_dir or config.get("DATA_DIR") or DEFAULT_DATA_DIR
    if not os.path.exists(data_dir):
        # Fallback to local workspace directory if Zerodha directory is not found
        if os.path.exists(DEFAULT_DATA_DIR):
            data_dir = DEFAULT_DATA_DIR
        else:
            data_dir = FALLBACK_DATA_DIR
            os.makedirs(data_dir, exist_ok=True)
            
    logger.info(f"Target Parquet Storage Directory: {data_dir}")

    # Target date range (Kotak Neo limits fromDate to within the last 5 years)
    target_start = datetime.strptime(args.from_date, "%Y-%m-%d")
    target_end = datetime.strptime(args.to_date, "%Y-%m-%d")

    # Earliest date allowed by Kotak Neo is 5 years from current date
    earliest_allowed = datetime.now() - timedelta(days=5 * 365 - 3)
    if target_start < earliest_allowed:
        logger.info(f"Clamped from-date from {target_start.strftime('%Y-%m-%d')} to Kotak's 5-year maximum limit: {earliest_allowed.strftime('%Y-%m-%d')}")
        target_start = earliest_allowed

    logger.info(f"Target Missing Gap Date Window: {target_start.strftime('%Y-%m-%d')} to {target_end.strftime('%Y-%m-%d')}")

    # 2. Check credentials
    if not args.dry_run and not config.get("KOTAK_CONSUMER_KEY"):
        logger.error(
            "\n[MISSING CREDENTIALS] No KOTAK_CONSUMER_KEY found in kotak_credentials.env!\n"
            "Please open `kotak_credentials.env` and paste your Consumer Key & Secret from the Kotak Neo Developer Portal.\n"
            "Run with `--dry-run` if you want to inspect existing gaps without API keys."
        )
        sys.exit(1)

    # 3. Initialize Kotak Client & Scrip Resolver
    client_mgr = None
    if config.get("KOTAK_CONSUMER_KEY"):
        try:
            client_mgr = KotakClientManager(config)
            client_mgr.authenticate()
        except Exception as e:
            logger.error(f"Failed to initialize Kotak API client: {e}")
            if not args.dry_run:
                sys.exit(1)

    scrip_resolver = ScripResolver(client_mgr) if client_mgr else None

    # 4. Determine symbol list
    if args.symbols:
        symbols = [s.strip().upper().replace(".NS", "") for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = get_prioritized_symbol_list(data_dir, scrip_resolver, existing_only=args.existing_only)

    logger.info(f"Total symbols scheduled for processing: {len(symbols)}")

    # 5. Process symbols
    success_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, symbol in enumerate(symbols, 1):
        clean_sym = symbol.upper().replace(".NS", "").strip()
        parquet_file = os.path.join(data_dir, f"{clean_sym}.parquet")

        # Inspect existing file coverage
        min_dt, max_dt, count = inspect_existing_file(parquet_file)

        # Gap evaluation
        if not args.force and min_dt is not None:
            # If the file already starts on or before target_start + 1 day
            if min_dt <= (target_start + timedelta(days=1)):
                logger.info(f"[{idx}/{len(symbols)}] [{clean_sym}] Already complete (min: {min_dt.strftime('%Y-%m-%d')}, rows: {count:,}). Skipping.")
                skipped_count += 1
                continue
            # Missing gap is from target_start up to min_dt
            gap_end = min(target_end, min_dt - timedelta(minutes=1))
        else:
            gap_end = target_end

        if target_start >= gap_end:
            logger.info(f"[{idx}/{len(symbols)}] [{clean_sym}] Date range already satisfied. Skipping.")
            skipped_count += 1
            continue

        neo_token = scrip_resolver.get_token(clean_sym) if scrip_resolver else None
        if not neo_token:
            logger.warning(f"[{idx}/{len(symbols)}] [{clean_sym}] Scrip token not found in Kotak master. Skipping.")
            failed_count += 1
            continue

        chunks = generate_date_chunks(target_start, gap_end, chunk_days=args.chunk_days)
        logger.info(
            f"[{idx}/{len(symbols)}] [{clean_sym}] Token: {neo_token} | "
            f"Need {target_start.strftime('%Y-%m-%d')} to {gap_end.strftime('%Y-%m-%d')} ({len(chunks)} chunks)"
        )

        if args.dry_run:
            continue

        # Fetch chunks for this symbol
        stock_dfs = []
        for c_idx, (c_start, c_end) in enumerate(chunks, 1):
            time.sleep(args.sleep)
            res = client_mgr.fetch_historical_candles(
                neo_symbol=neo_token,
                interval="1min",
                from_date=c_start,
                to_date=c_end
            )
            df_chunk = parse_candles_to_df(res)
            if not df_chunk.empty:
                stock_dfs.append(df_chunk)
                logger.info(f"    -> Chunk {c_idx}/{len(chunks)} ({c_start} to {c_end}): {len(df_chunk):,} candles")
            else:
                logger.debug(f"    -> Chunk {c_idx}/{len(chunks)} ({c_start} to {c_end}): 0 candles (weekend/unlisted)")

        if stock_dfs:
            combined_new_df = pd.concat(stock_dfs, ignore_index=True)
            ok, total_rows, msg = stitch_and_save_parquet(parquet_file, combined_new_df)
            if ok:
                new_min, new_max, _ = inspect_existing_file(parquet_file)
                logger.info(
                    f"[{idx}/{len(symbols)}] [{clean_sym}] STITCHED SUCCESSFULLY! "
                    f"Total: {total_rows:,} rows (Date span: {new_min.strftime('%Y-%m-%d')} to {new_max.strftime('%Y-%m-%d')})"
                )
                success_count += 1
            else:
                logger.error(f"[{idx}/{len(symbols)}] [{clean_sym}] Stitching error: {msg}")
                failed_count += 1
        else:
            logger.warning(f"[{idx}/{len(symbols)}] [{clean_sym}] No historical data returned for requested period.")
            skipped_count += 1

    print("\n" + "=" * 70)
    print(" HISTORICAL SYNC COMPLETE ")
    print(f" Total Processed : {len(symbols)}")
    print(f" Successfully Stitched : {success_count}")
    print(f" Already Up-to-Date/Skipped : {skipped_count}")
    print(f" Failed/Unresolved : {failed_count}")
    print("=" * 70)


if __name__ == "__main__":
    main()

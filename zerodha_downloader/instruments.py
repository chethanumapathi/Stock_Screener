import io
import logging
from pathlib import Path
import pandas as pd
import requests
from kiteconnect import KiteConnect

import config

logger = logging.getLogger(__name__)

INSTRUMENTS_CACHE_DIR = config.DATA_DIR / "instruments"
INSTRUMENTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
NIFTY500_CACHE_FILE = INSTRUMENTS_CACHE_DIR / "nifty500_instruments.csv"


class Nifty500Instruments:
    """
    Handles fetching of official Nifty 500 constituent symbols from NSE India
    and mapping them to Zerodha Kite Connect instrument tokens.
    """

    def __init__(self, kite: KiteConnect):
        self.kite = kite

    @staticmethod
    def fetch_nse_nifty500_symbols() -> pd.DataFrame:
        """
        Download the official Nifty 500 constituent list from NSE India.
        Returns a DataFrame containing at least ['Symbol', 'Company Name', 'Industry'].
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        print("Fetching official Nifty 500 list from NSE...")
        try:
            session = requests.Session()
            # Visit main NSE page first to set session cookies
            session.get("https://www.nseindia.com", headers=headers, timeout=10)
            response = session.get(config.NSE_NIFTY_500_URL, headers=headers, timeout=15)
            response.raise_for_status()

            df = pd.read_csv(io.StringIO(response.text))
            # Normalize column names
            df.columns = [c.strip() for c in df.columns]
            print(f"Successfully fetched {len(df)} Nifty 500 constituents from NSE.")
            return df
        except Exception as e:
            logger.warning(f"Could not fetch directly from NSE archives ({e}). Trying fallback URL...")
            # Fallback URL if archives URL is slow or blocked
            fallback_url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
            try:
                response = requests.get(fallback_url, headers=headers, timeout=15)
                response.raise_for_status()
                df = pd.read_csv(io.StringIO(response.text))
                df.columns = [c.strip() for c in df.columns]
                print(f"Successfully fetched {len(df)} Nifty 500 constituents from fallback.")
                return df
            except Exception as e2:
                raise RuntimeError(
                    f"Failed to fetch Nifty 500 list from NSE: {e2}. "
                    "Please check internet connection or provide a local CSV file."
                )

    def get_instruments(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Loads mapped Nifty 500 instruments with Zerodha instrument_tokens.
        Uses local cached CSV if available, unless force_refresh=True.
        """
        if not force_refresh and NIFTY500_CACHE_FILE.exists():
            print(f"Loading cached Nifty 500 instrument mapping from {NIFTY500_CACHE_FILE}...")
            df = pd.read_csv(NIFTY500_CACHE_FILE)
            if not df.empty and "instrument_token" in df.columns:
                print(f"Loaded {len(df)} mapped instruments.")
                return df

        # Step 1: Fetch official Nifty 500 list
        nifty_df = self.fetch_nse_nifty500_symbols()
        nifty_symbols = set(nifty_df["Symbol"].str.strip().str.upper())

        # Step 2: Fetch all NSE instruments from Zerodha
        print("Fetching full NSE instruments dump from Zerodha Kite Connect...")
        all_instruments = self.kite.instruments("NSE")
        instruments_df = pd.DataFrame(all_instruments)

        # Filter for NSE Equities (EQ)
        eq_instruments = instruments_df[
            (instruments_df["segment"] == "NSE") &
            (instruments_df["instrument_type"] == "EQ")
        ].copy()

        eq_instruments["tradingsymbol"] = eq_instruments["tradingsymbol"].str.strip().str.upper()

        # Step 3: Match Nifty 500 symbols with Zerodha instruments
        mapped_df = eq_instruments[eq_instruments["tradingsymbol"].isin(nifty_symbols)].copy()

        # Merge with company details from NSE
        nifty_df_renamed = nifty_df.rename(columns={"Symbol": "tradingsymbol"})
        nifty_df_renamed["tradingsymbol"] = nifty_df_renamed["tradingsymbol"].str.strip().str.upper()

        merged_df = pd.merge(
            mapped_df,
            nifty_df_renamed[["tradingsymbol", "Company Name", "Industry", "ISIN Code"]],
            on="tradingsymbol",
            how="left"
        )

        # Clean up and select key columns
        cols = [
            "instrument_token",
            "tradingsymbol",
            "Company Name",
            "Industry",
            "ISIN Code",
            "segment",
            "tick_size",
            "lot_size",
        ]
        available_cols = [c for c in cols if c in merged_df.columns]
        result_df = merged_df[available_cols].sort_values("tradingsymbol").reset_index(drop=True)

        # Cache to disk
        result_df.to_csv(NIFTY500_CACHE_FILE, index=False)
        print(f"Successfully mapped and cached {len(result_df)} Nifty 500 instruments to {NIFTY500_CACHE_FILE}")

        # Log any symbols that were in Nifty 500 list but not found in Zerodha EQ
        missing_symbols = nifty_symbols - set(result_df["tradingsymbol"])
        if missing_symbols:
            logger.info(f"Unmatched symbols ({len(missing_symbols)}): {missing_symbols}")

        return result_df


def load_nifty500_instruments(kite: KiteConnect, force_refresh: bool = False) -> pd.DataFrame:
    """Helper to fetch and return mapped Nifty 500 instruments DataFrame."""
    manager = Nifty500Instruments(kite)
    return manager.get_instruments(force_refresh=force_refresh)


NSE_ALL_CACHE_FILE = INSTRUMENTS_CACHE_DIR / "nse_all_equities.csv"


class NSEAllEquitiesInstruments:
    """
    Downloads the official 'NSE All Equities' master file (EQUITY_L.csv) from NSE,
    detects newly listed stocks compared to previous runs, and maps all active
    EQ series stocks to Zerodha Kite Connect instrument tokens.
    """

    def __init__(self, kite: KiteConnect):
        self.kite = kite

    @staticmethod
    def fetch_nse_all_equities() -> pd.DataFrame:
        """
        Download official EQUITY_L.csv from NSE archives.
        """
        urls = [
            config.NSE_ALL_EQUITIES_URL,
            "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
        ]
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        print("Checking NSE All Equities master file (EQUITY_L.csv) from NSE...")
        last_err = None
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()

                df = pd.read_csv(io.StringIO(response.text))
                df.columns = [c.strip() for c in df.columns]

                # Filter for active EQ series
                if "SERIES" in df.columns:
                    df = df[df["SERIES"].str.strip() == "EQ"].copy()

                df["SYMBOL"] = df["SYMBOL"].str.strip().str.upper()
                print(f"Successfully loaded {len(df)} active EQ stocks from NSE.")
                return df
            except Exception as e:
                last_err = e
                logger.warning(f"Error fetching from {url}: {e}")

        raise RuntimeError(f"Failed to fetch NSE All Equities: {last_err}")

    def get_instruments(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Downloads fresh NSE All Equities master list, detects new additions,
        and maps all symbols to Zerodha Kite Connect instrument tokens.
        Uses local cached CSV if available, unless force_refresh=True.
        """
        if not force_refresh and NSE_ALL_CACHE_FILE.exists():
            print(f"Loading cached NSE All Equities instrument mapping from {NSE_ALL_CACHE_FILE}...")
            df = pd.read_csv(NSE_ALL_CACHE_FILE)
            if not df.empty and "instrument_token" in df.columns:
                print(f"Loaded {len(df)} mapped instruments.")
                return df

        # Step 1: Download fresh EQUITY_L from NSE
        nse_df = self.fetch_nse_all_equities()
        current_symbols = set(nse_df["SYMBOL"])

        # Step 2: Compare with previous cache to detect new listings/IPOs
        if NSE_ALL_CACHE_FILE.exists():
            try:
                prev_df = pd.read_csv(NSE_ALL_CACHE_FILE)
                if not prev_df.empty and "tradingsymbol" in prev_df.columns:
                    prev_symbols = set(prev_df["tradingsymbol"].str.strip().str.upper())
                    new_additions = current_symbols - prev_symbols
                    delisted = prev_symbols - current_symbols

                    if new_additions:
                        print(f"\n{'='*70}")
                        print(f"[!] NEW NSE LISTINGS DETECTED: {len(new_additions)} new stock(s) added to NSE:")
                        for s in sorted(new_additions):
                            comp = nse_df[nse_df["SYMBOL"] == s]["NAME OF COMPANY"].values
                            comp_name = comp[0] if len(comp) > 0 else ""
                            print(f"    + {s:<15} ({comp_name})")
                        print(f"{'='*70}\n")
                    else:
                        print("No new stock listings detected on NSE since last check.")

                    if delisted:
                        print(f"[*] {len(delisted)} stock(s) delisted/suspended from NSE: {', '.join(sorted(delisted))}")
            except Exception as e:
                logger.debug(f"Could not compare with previous cache: {e}")

        # Step 3: Fetch Zerodha NSE instruments dump
        print("Fetching Zerodha NSE instruments mapping...")
        all_instruments = self.kite.instruments("NSE")
        inst_df = pd.DataFrame(all_instruments)

        eq_instruments = inst_df[
            (inst_df["segment"] == "NSE") &
            (inst_df["instrument_type"] == "EQ")
        ].copy()
        eq_instruments["tradingsymbol"] = eq_instruments["tradingsymbol"].str.strip().str.upper()

        # Step 4: Merge NSE master with Zerodha instruments
        nse_df_renamed = nse_df.rename(columns={"SYMBOL": "tradingsymbol"})
        merged_df = pd.merge(
            nse_df_renamed,
            eq_instruments[["tradingsymbol", "instrument_token", "tick_size", "lot_size"]],
            on="tradingsymbol",
            how="inner",
        )

        col_map = {
            "NAME OF COMPANY": "company_name",
            "ISIN NUMBER": "isin",
            "DATE OF LISTING": "listing_date",
            "FACE VALUE": "face_value",
        }
        for old_c, new_c in col_map.items():
            if old_c in merged_df.columns:
                merged_df = merged_df.rename(columns={old_c: new_c})

        cols = [
            "instrument_token",
            "tradingsymbol",
            "company_name",
            "isin",
            "listing_date",
            "face_value",
            "tick_size",
            "lot_size",
        ]
        available_cols = [c for c in cols if c in merged_df.columns]
        result_df = merged_df[available_cols].sort_values("tradingsymbol").reset_index(drop=True)

        # Cache to disk
        result_df.to_csv(NSE_ALL_CACHE_FILE, index=False)
        print(f"Successfully mapped and cached {len(result_df)} NSE All Equities instruments to {NSE_ALL_CACHE_FILE}")

        return result_df


def load_all_equities_instruments(kite: KiteConnect, force_refresh: bool = False) -> pd.DataFrame:
    """Helper to fetch and return mapped NSE All Equities DataFrame."""
    manager = NSEAllEquitiesInstruments(kite)
    return manager.get_instruments(force_refresh=force_refresh)

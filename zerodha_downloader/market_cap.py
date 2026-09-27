import io
import logging
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd
import yfinance as yf
from kiteconnect import KiteConnect
from tqdm import tqdm

import config

logger = logging.getLogger(__name__)


class MarketCapUniverse:
    """
    Downloads the master 'NSE All Equities' list (EQUITY_L.csv) from NSE,
    computes live market capitalization dynamically for all companies,
    filters for companies above a specified cutoff (e.g. >= 2000 Crores),
    and maps them to Zerodha Kite Connect instrument tokens.
    """

    def __init__(self, kite: KiteConnect, min_crores: float = config.DEFAULT_MIN_MCAP_CRORES):
        self.kite = kite
        self.min_crores = float(min_crores)
        self.today_str = datetime.now().strftime("%Y-%m-%d")
        self.universe_dir = config.UNIVERSE_DIR
        self.universe_dir.mkdir(parents=True, exist_ok=True)

        self.filtered_cache_file = self.universe_dir / f"mcap_above_{int(self.min_crores)}cr_{self.today_str}.csv"
        self.all_mcap_cache_file = self.universe_dir / f"mcap_all_nse_{self.today_str}.csv"

    @staticmethod
    def fetch_nse_all_equities() -> pd.DataFrame:
        """
        Download the official master list of all equities listed on the National Stock Exchange.
        Source: https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
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

        print("Downloading official 'NSE All Equities' master file (EQUITY_L.csv) from NSE...")
        last_err = None
        for url in urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    content = resp.read().decode("utf-8")

                df = pd.read_csv(io.StringIO(content))
                df.columns = [c.strip() for c in df.columns]

                # Filter for regular equity series (EQ)
                if "SERIES" in df.columns:
                    df = df[df["SERIES"].str.strip() == "EQ"].copy()

                df["SYMBOL"] = df["SYMBOL"].str.strip().str.upper()
                print(f"Successfully loaded {len(df)} active EQ stocks from NSE.")
                return df
            except Exception as e:
                last_err = e
                logger.warning(f"Failed to fetch from {url}: {e}. Retrying fallback...")

        raise RuntimeError(f"Could not download NSE All Equities file from any URL: {last_err}")

    def _fetch_single_mcap(self, symbol: str) -> Tuple[str, Optional[float]]:
        """Fetch market cap for a single NSE ticker in Crores."""
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            mc = ticker.fast_info.market_cap
            if mc and mc > 0:
                return symbol, round(mc / 1e7, 2)  # Convert to INR Crores
        except Exception:
            pass
        return symbol, None

    def compute_all_market_caps(self, symbols: List[str], max_workers: int = 40) -> Dict[str, float]:
        """
        Calculates market capitalization for all given symbols in parallel.
        Uses cached full results for today if available.
        """
        # Check if full scan for today is already cached
        if self.all_mcap_cache_file.exists():
            print(f"Loading today's full NSE market cap cache from {self.all_mcap_cache_file.name}...")
            cached_df = pd.read_csv(self.all_mcap_cache_file)
            if not cached_df.empty and "SYMBOL" in cached_df.columns and "market_cap_crores" in cached_df.columns:
                return dict(zip(cached_df["SYMBOL"], cached_df["market_cap_crores"]))

        print(f"\nComputing live market capitalization for {len(symbols)} NSE stocks ({max_workers} threads)...")
        mcap_dict = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._fetch_single_mcap, sym): sym for sym in symbols}
            with tqdm(total=len(symbols), desc="Scanning Market Caps", unit="stock", dynamic_ncols=True) as pbar:
                for future in as_completed(futures):
                    sym, mcap = future.result()
                    if mcap is not None:
                        mcap_dict[sym] = mcap
                    pbar.update(1)

        # Cache full results for today
        records = [{"SYMBOL": s, "market_cap_crores": mc} for s, mc in mcap_dict.items()]
        pd.DataFrame(records).to_csv(self.all_mcap_cache_file, index=False)
        print(f"Saved today's market cap cache to {self.all_mcap_cache_file.name}")

        return mcap_dict

    def get_qualified_universe(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Returns a DataFrame of all NSE companies with market cap >= min_crores,
        mapped to Zerodha Kite Connect instrument tokens.
        """
        if not force_refresh and self.filtered_cache_file.exists():
            print(f"Loading today's qualified universe from {self.filtered_cache_file}...")
            df = pd.read_csv(self.filtered_cache_file)
            if not df.empty and "instrument_token" in df.columns:
                print(f"Loaded {len(df)} qualified stocks with Market Cap >= Rs. {self.min_crores:,.0f} Cr.")
                return df

        # Step 1: Download all active NSE listed equities
        equities_df = self.fetch_nse_all_equities()
        symbols = equities_df["SYMBOL"].tolist()

        # Step 2: Compute market caps
        mcap_dict = self.compute_all_market_caps(symbols, max_workers=40)

        # Step 3: Filter for market_cap >= min_crores
        equities_df["market_cap_crores"] = equities_df["SYMBOL"].map(mcap_dict)
        qualified_df = equities_df[equities_df["market_cap_crores"] >= self.min_crores].copy()
        qualified_df = qualified_df.sort_values("market_cap_crores", ascending=False).reset_index(drop=True)

        print(
            f"\nMarket Cap Filtering Results:\n"
            f"  * Total NSE Equities Scanned : {len(equities_df)}\n"
            f"  * Stocks with Valid Mcap     : {len(mcap_dict)}\n"
            f"  * Qualified (>= Rs. {self.min_crores:,.0f} Cr)   : {len(qualified_df)} stocks\n"
            f"  * Excluded (< Rs. {self.min_crores:,.0f} Cr)    : {len(mcap_dict) - len(qualified_df)} stocks"
        )

        # Step 4: Map to Zerodha Kite Connect instrument tokens
        print("\nMapping qualified stocks to Zerodha Kite Connect instrument tokens...")
        all_instruments = self.kite.instruments("NSE")
        instruments_df = pd.DataFrame(all_instruments)

        eq_instruments = instruments_df[
            (instruments_df["segment"] == "NSE") &
            (instruments_df["instrument_type"] == "EQ")
        ].copy()
        eq_instruments["tradingsymbol"] = eq_instruments["tradingsymbol"].str.strip().str.upper()

        # Merge with Zerodha instruments
        qualified_df = qualified_df.rename(columns={"SYMBOL": "tradingsymbol"})
        merged_df = pd.merge(
            qualified_df,
            eq_instruments[["tradingsymbol", "instrument_token", "tick_size", "lot_size"]],
            on="tradingsymbol",
            how="inner",
        )

        # Rename for clean output
        col_rename = {
            "NAME OF COMPANY": "company_name",
            "ISIN NUMBER": "isin",
            "FACE VALUE": "face_value",
        }
        for old, new in col_rename.items():
            if old in merged_df.columns:
                merged_df = merged_df.rename(columns={old: new})

        # Desired columns
        cols = [
            "instrument_token",
            "tradingsymbol",
            "market_cap_crores",
            "company_name",
            "isin",
            "tick_size",
            "lot_size",
        ]
        available_cols = [c for c in cols if c in merged_df.columns]
        result_df = merged_df[available_cols].sort_values("market_cap_crores", ascending=False).reset_index(drop=True)

        # Save to cache
        result_df.to_csv(self.filtered_cache_file, index=False)
        print(f"Successfully saved qualified universe ({len(result_df)} stocks) to {self.filtered_cache_file}")

        return result_df


def load_mcap_universe(
    kite: KiteConnect,
    min_crores: float = config.DEFAULT_MIN_MCAP_CRORES,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Helper to instantiate manager and return qualified stocks DataFrame."""
    manager = MarketCapUniverse(kite=kite, min_crores=min_crores)
    return manager.get_qualified_universe(force_refresh=force_refresh)


if __name__ == "__main__":
    from auth import KiteAuthManager

    auth = KiteAuthManager()
    kite_client = auth.get_kite_session()
    df = load_mcap_universe(kite=kite_client, min_crores=2000)
    print(f"\nTop 10 Stocks by Market Cap:\n{df.head(10)[['tradingsymbol', 'market_cap_crores', 'company_name']]}")

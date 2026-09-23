"""
live_sync_service.py
====================
Real-time Live Market Data Synchronizer for Stock Screener & Order Flow Engine.

Capabilities:
1. Continuous background synchronization during Indian Market hours (09:15 - 15:30 IST).
2. Dual-Target Persistence:
   - Stitches newly closed 1-minute candles directly into `C:\\Zerodha Historical Data\\data\\minute\\{symbol}.parquet`.
   - Simultaneously feeds candles into `OrderFlowEngine` so Footprint Delta bars,
     CVD (Cumulative Volume Delta), and multi-timeframe aggregations (3m, 5m, 15m, 1h) are updated live.
3. On-Demand Sync: Allows the Screener (`/api/screen`) to trigger immediate up-to-the-minute sync
   for target segments (Nifty 50, F&O, Watchlist) before executing strategies.
4. Robust rate-limit pacing (0.35s sleep) and DuckDB atomic parquet stitching.
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

import pandas as pd
import duckdb

import fetch_kotak_history as fkh
import sync_minute_data as smd

IST = timezone(timedelta(hours=5, minutes=30))
ZERODHA_MINUTE_DIR = r"C:\Zerodha Historical Data\data\minute"

logger = logging.getLogger("live_sync")
if not logger.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] [LiveSync] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(h)
logger.setLevel(logging.INFO)


def is_market_open(dt: Optional[datetime] = None) -> bool:
    """Checks if regular trading hours are currently active (Mon-Fri 09:15 - 15:30 IST)."""
    if dt is None:
        now = datetime.now(IST)
    else:
        now = dt if dt.tzinfo else dt.replace(tzinfo=IST)

    if now.weekday() >= 5: # Saturday / Sunday
        return False

    mkt_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    mkt_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return mkt_open <= now <= mkt_close


class LiveSyncService:
    """Manages real-time intraday data synchronization across Kotak Neo, Parquet files, and OrderFlow."""

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, orderflow_engine=None):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = LiveSyncService(orderflow_engine=orderflow_engine)
            elif orderflow_engine and cls._instance.orderflow_engine is None:
                cls._instance.orderflow_engine = orderflow_engine
            return cls._instance

    def __init__(self, orderflow_engine=None):
        self.orderflow_engine = orderflow_engine
        self.config = fkh.load_env_config("kotak_credentials.env")
        self.client_mgr: Optional[fkh.KotakClientManager] = None
        self.scrip_resolver: Optional[fkh.ScripResolver] = None
        
        try:
            if self.config.get("KOTAK_CONSUMER_KEY"):
                self.client_mgr = fkh.KotakClientManager(self.config)
                self.scrip_resolver = fkh.ScripResolver(self.client_mgr)
                logger.info("LiveSyncService initialized with Kotak Neo credentials.")
        except Exception as e:
            logger.warning(f"LiveSyncService Kotak initialization note: {e}")

        self.is_active = False
        self.is_running = False
        self.target_segment = 'nifty50' # 'nifty50', 'fno', 'nifty500', 'watchlist', 'all'
        self.custom_symbols: List[str] = []
        self.sync_interval = 60 # seconds
        self.worker_thread: Optional[threading.Thread] = None
        
        self.last_sync_time: Optional[str] = None
        self.last_sync_duration: float = 0.0
        self.last_updated_count: int = 0
        self.last_total_count: int = 0
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()

    def get_status(self) -> Dict[str, Any]:
        """Returns current operational status and diagnostics."""
        with self._lock:
            return {
                "is_active": self.is_active,
                "is_running": self.is_running,
                "target_segment": self.target_segment,
                "sync_interval_seconds": self.sync_interval,
                "last_sync_time": self.last_sync_time,
                "last_sync_duration_s": round(self.last_sync_duration, 2),
                "last_updated_count": self.last_updated_count,
                "last_total_count": self.last_total_count,
                "last_error": self.last_error,
                "is_market_open": is_market_open(),
                "has_kotak_client": bool(self.client_mgr and self.scrip_resolver)
            }

    def start_background_sync(self, target_segment: str = 'nifty50', interval: int = 60) -> bool:
        """Starts continuous background live sync worker thread."""
        with self._lock:
            self.target_segment = target_segment
            self.sync_interval = max(30, interval)
            self.is_active = True

            if self.worker_thread and self.worker_thread.is_alive():
                logger.info(f"LiveSync worker already running. Updated segment to: {self.target_segment}, interval: {self.sync_interval}s")
                return True

            self.worker_thread = threading.Thread(target=self._run_worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info(f"LiveSync background worker started (Segment: {self.target_segment}, Interval: {self.sync_interval}s)")
            return True

    def stop_background_sync(self) -> bool:
        """Stops continuous background live sync worker."""
        with self._lock:
            self.is_active = False
        logger.info("LiveSync background worker stop requested.")
        return True

    def _resolve_symbols_for_segment(self, segment: str, custom: Optional[List[str]] = None) -> List[str]:
        """Resolves ticker symbols for a chosen segment."""
        if custom and len(custom) > 0:
            return [s.strip().upper().replace('.NS', '') for s in custom if s.strip()]

        seg = segment.lower().strip()
        if seg == 'nifty50':
            return smd.get_prioritized_symbols(tier='nifty50')
        elif seg == 'nifty500':
            return smd.get_prioritized_symbols(tier='nifty500')
        elif seg == 'fno':
            fno_path = os.path.join(smd.DATA_DIR, 'fno.csv')
            if os.path.exists(fno_path):
                df_fno = pd.read_csv(fno_path)
                return [s.strip().upper() for s in df_fno['Symbol'].dropna().tolist()]
            return smd.get_prioritized_symbols(tier='nifty50')
        elif seg == 'all':
            return smd.get_prioritized_symbols(tier='all')
        else:
            return smd.get_prioritized_symbols(tier='nifty50')

    def sync_symbols_now(self, symbols: List[str], target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronously fetches intraday 1-minute candles from Kotak Neo for given symbols,
        stitches them atomically into Parquet files, and ingests them into OrderFlowEngine.
        """
        if not (self.client_mgr and self.scrip_resolver):
            return {
                "success": False,
                "error": "Kotak Neo API credentials not configured",
                "updated": 0,
                "total": len(symbols)
            }

        now_dt = datetime.now(IST)
        today_str = now_dt.strftime('%Y-%m-%d')
        sync_date_str = target_date if target_date else today_str

        # If syncing today or earlier, to_date must not be in the future
        to_date_str = min(sync_date_str, today_str)
        from_date_str = sync_date_str

        start_time = time.time()
        updated_symbols = []
        failed_symbols = []

        with self._lock:
            self.is_running = True

        try:
            total = len(symbols)
            logger.info(f"Syncing live intraday 1-minute data for {total} symbols ({from_date_str} to {to_date_str})...")

            for idx, sym in enumerate(symbols, 1):
                clean_sym = sym.strip().upper().replace('.NS', '')
                tok = self.scrip_resolver.get_token(clean_sym)
                if not tok:
                    continue

                p_file = os.path.join(ZERODHA_MINUTE_DIR, f"{clean_sym}.parquet")
                time.sleep(0.35)

                try:
                    res = self.client_mgr.fetch_historical_candles(
                        neo_symbol=tok,
                        interval="1min",
                        from_date=from_date_str,
                        to_date=to_date_str
                    )
                    df = fkh.parse_candles_to_df(res)
                    if not df.empty:
                        # 1. Atomic stitch to Parquet file
                        ok, total_rows, msg = fkh.stitch_and_save_parquet(p_file, df, symbol=clean_sym)
                        if ok:
                            updated_symbols.append(clean_sym)
                        else:
                            failed_symbols.append(clean_sym)

                        # 2. Ingest into OrderFlowEngine for footprint delta & CVD update
                        if self.orderflow_engine:
                            try:
                                self.orderflow_engine.ingest_external_candles(clean_sym, df)
                            except Exception as of_err:
                                logger.debug(f"OrderFlow ingest exception for {clean_sym}: {of_err}")
                except Exception as ex:
                    logger.debug(f"Live sync error for {clean_sym}: {ex}")
                    failed_symbols.append(clean_sym)

            duration = time.time() - start_time
            with self._lock:
                self.last_sync_time = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
                self.last_sync_duration = duration
                self.last_updated_count = len(updated_symbols)
                self.last_total_count = total
                self.last_error = None

            logger.info(f"Live sync complete: {len(updated_symbols)}/{total} symbols updated in {duration:.1f}s.")
            return {
                "success": True,
                "updated": len(updated_symbols),
                "total": total,
                "duration_s": round(duration, 2),
                "updated_symbols": updated_symbols,
                "failed_symbols": failed_symbols,
                "sync_time": self.last_sync_time
            }
        except Exception as e:
            with self._lock:
                self.last_error = str(e)
            logger.error(f"Live sync exception: {e}")
            return {
                "success": False,
                "error": str(e),
                "updated": len(updated_symbols),
                "total": len(symbols)
            }
        finally:
            with self._lock:
                self.is_running = False

    def sync_segment_now(self, segment: str = 'nifty50', custom_symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Convenience function to trigger an immediate sync for a segment."""
        symbols = self._resolve_symbols_for_segment(segment, custom=custom_symbols)
        return self.sync_symbols_now(symbols)

    def _run_worker_loop(self):
        """Continuous background execution loop."""
        while self.is_active:
            try:
                # Only poll automatically during market hours, or if explicitly requested
                if is_market_open():
                    symbols = self._resolve_symbols_for_segment(self.target_segment, custom=self.custom_symbols)
                    if symbols:
                        self.sync_symbols_now(symbols)
                else:
                    logger.debug("Market closed. Live sync worker sleeping...")

                # Sleep until next sync interval
                for _ in range(int(self.sync_interval)):
                    if not self.is_active:
                        break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Error in LiveSync worker loop: {e}")
                time.sleep(5)
        logger.info("LiveSync worker loop exited.")

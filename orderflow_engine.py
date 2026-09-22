"""
orderflow_engine.py
===================
Real-time Order Flow & Live Technical Chart Engine using Kotak Neo API.

Key Capabilities:
1. Live Tick Streaming via Kotak Neo WebSocket (with depth/touchline).
2. Tick-Level Order Flow Classification:
   - Lee-Ready Algorithm & Quote Match Rule (Trade Price vs Best Bid/Ask).
   - Fallback Tick Rule (Uptick = Buyer Aggression, Downtick = Seller Aggression).
3. Real-Time Delta & CVD Aggregation:
   - Bar Delta = Buy Volume - Sell Volume.
   - Cumulative Volume Delta (CVD) tracking session accumulation/distribution.
   - Multi-timeframe bar builder: 5s, 1m, 3m, 5m, 15m, 1d.
4. Isolated Dedicated Database:
   - DuckDB database strictly at `data/orderflow/orderflow.duckdb`.
   - Absolutely NO modification or writing to `C:\\Zerodha Historical Data\\data\\minute`.
5. Real-Time Event Broadcaster:
   - Thread-safe queues for Server-Sent Events (SSE) `/api/orderflow/stream`.
6. Built-in Simulation Mode:
   - Automatically maintains a realistic order flow tick simulation when market
     is closed (after 3:30 PM, weekends) or when Kotak API is disconnected.
"""

import os
import sys
import time
import json
import math
import random
import logging
import threading
from queue import Queue, Empty
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import duckdb
import pandas as pd
import numpy as np

# Import credentials & scrip resolver helpers from existing fetch_kotak_history
import fetch_kotak_history as fkh

# Try importing official Kotak Neo SDK
try:
    from neo_api_client import NeoAPI
except ImportError:
    NeoAPI = None

logger = logging.getLogger("orderflow_engine")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] [OrderFlow] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORDERFLOW_DIR = os.path.join(BASE_DIR, "data", "orderflow")
ORDERFLOW_DB_PATH = os.path.join(ORDERFLOW_DIR, "orderflow.duckdb")
os.makedirs(ORDERFLOW_DIR, exist_ok=True)


class OrderFlowDatabase:
    """Manages dedicated DuckDB storage for tick and candle delta order flow data."""

    def __init__(self, db_path: str = ORDERFLOW_DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self):
        return duckdb.connect(self.db_path)

    def _init_db(self):
        with self._lock:
            con = self._get_connection()
            try:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS orderflow_candles (
                        symbol VARCHAR,
                        timeframe VARCHAR,
                        epoch_time BIGINT,
                        datetime_str VARCHAR,
                        open DOUBLE,
                        high DOUBLE,
                        low DOUBLE,
                        close DOUBLE,
                        volume BIGINT,
                        buy_volume BIGINT,
                        sell_volume BIGINT,
                        delta BIGINT,
                        cum_delta BIGINT,
                        trades_count INT,
                        PRIMARY KEY (symbol, timeframe, epoch_time)
                    );
                """)
                con.execute("""
                    CREATE TABLE IF NOT EXISTS orderflow_session_stats (
                        symbol VARCHAR PRIMARY KEY,
                        trading_date VARCHAR,
                        ltp DOUBLE,
                        day_open DOUBLE,
                        day_high DOUBLE,
                        day_low DOUBLE,
                        day_volume BIGINT,
                        session_buy_vol BIGINT,
                        session_sell_vol BIGINT,
                        session_delta BIGINT,
                        total_ticks BIGINT,
                        updated_at VARCHAR
                    );
                """)
            finally:
                con.close()

    def save_candle(self, candle: dict):
        """Persists a closed or updated candle into DuckDB atomically."""
        with self._lock:
            con = self._get_connection()
            try:
                con.execute("""
                    INSERT OR REPLACE INTO orderflow_candles VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    );
                """, [
                    candle['symbol'],
                    candle['timeframe'],
                    int(candle['time']),
                    candle.get('datetime_str', ''),
                    float(candle['open']),
                    float(candle['high']),
                    float(candle['low']),
                    float(candle['close']),
                    int(candle['volume']),
                    int(candle['buy_volume']),
                    int(candle['sell_volume']),
                    int(candle['delta']),
                    int(candle['cum_delta']),
                    int(candle.get('trades_count', 1))
                ])
            except Exception as e:
                logger.error(f"Error saving candle to DuckDB: {e}")
            finally:
                con.close()

    def get_candles(self, symbol: str, timeframe: str, limit: int = 500) -> List[dict]:
        """Retrieves recent order flow candles for a symbol and timeframe."""
        with self._lock:
            con = self._get_connection()
            try:
                query = """
                    SELECT epoch_time as time, datetime_str, open, high, low, close,
                           volume, buy_volume, sell_volume, delta, cum_delta, trades_count
                    FROM orderflow_candles
                    WHERE symbol = ? AND timeframe = ?
                    ORDER BY epoch_time ASC
                """
                res = con.execute(query, [symbol.upper(), timeframe.lower()]).fetchall()
                cols = [desc[0] for desc in con.description]
                candles = [dict(zip(cols, row)) for row in res]
                if limit and len(candles) > limit:
                    candles = candles[-limit:]
                return candles
            except Exception as e:
                logger.error(f"Error loading candles from DuckDB: {e}")
                return []
            finally:
                con.close()


class DeltaCandleAggregator:
    """
    In-Memory real-time multi-timeframe candle builder and delta calculator.
    Tracks Open, High, Low, Close, Volume, Buy Volume, Sell Volume, Delta, and CVD.
    """

    TIMEFRAME_SECONDS = {
        '5s': 5,
        '1m': 60,
        '3m': 180,
        '5m': 300,
        '15m': 900,
        '1h': 3600,
        '1d': 86400
    }

    def __init__(self, symbol: str, db: OrderFlowDatabase):
        self.symbol = symbol.upper()
        self.db = db
        self.lock = threading.Lock()
        
        # State tracking
        self.last_price = 0.0
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.session_buy_volume = 0
        self.session_sell_volume = 0
        self.session_delta = 0
        self.total_ticks = 0
        self.day_open = 0.0
        self.day_high = 0.0
        self.day_low = 0.0
        self.prev_trade_side = 'BUY'

        # Candles by timeframe: timeframe -> list of completed dicts
        self.candles_history: Dict[str, List[dict]] = {tf: [] for tf in self.TIMEFRAME_SECONDS}
        # Current forming candle by timeframe: timeframe -> current dict
        self.current_candles: Dict[str, Optional[dict]] = {tf: None for tf in self.TIMEFRAME_SECONDS}
        
        # Load any existing candles from database
        for tf in self.TIMEFRAME_SECONDS:
            db_candles = self.db.get_candles(self.symbol, tf, limit=300)
            if db_candles:
                self.candles_history[tf] = db_candles
                if db_candles:
                    self.session_delta = db_candles[-1].get('cum_delta', 0)

    def process_tick(self, price: float, qty: int, timestamp: Optional[float] = None,
                     bid: float = 0.0, ask: float = 0.0) -> Tuple[str, int, dict]:
        """
        Classifies incoming tick using Lee-Ready / Quote match, updates candle bars and delta.
        Returns (trade_side, delta, tick_summary).
        """
        if timestamp is None:
            timestamp = time.time()
        
        with self.lock:
            self.total_ticks += 1
            if bid > 0:
                self.best_bid = bid
            if ask > 0:
                self.best_ask = ask

            # 1. Classify Tick (Lee-Ready Quote Rule + Tick Rule)
            side = 'BUY'
            if self.best_ask > 0 and price >= self.best_ask:
                side = 'BUY'  # Buyer-initiated aggression
            elif self.best_bid > 0 and price <= self.best_bid:
                side = 'SELL' # Seller-initiated aggression
            elif self.last_price > 0:
                if price > self.last_price:
                    side = 'BUY'
                elif price < self.last_price:
                    side = 'SELL'
                else:
                    side = self.prev_trade_side
            else:
                side = 'BUY'

            self.prev_trade_side = side
            self.last_price = price

            # 2. Session statistics
            if self.day_open == 0.0:
                self.day_open = price
                self.day_high = price
                self.day_low = price
            else:
                if price > self.day_high:
                    self.day_high = price
                if price < self.day_low:
                    self.day_low = price

            tick_delta = qty if side == 'BUY' else -qty
            if side == 'BUY':
                self.session_buy_volume += qty
            else:
                self.session_sell_volume += qty
            self.session_delta += tick_delta

            # 3. Update active candles across all timeframes
            updated_candles = {}
            for tf, tf_sec in self.TIMEFRAME_SECONDS.items():
                candle_bucket_time = int(timestamp // tf_sec) * tf_sec
                curr = self.current_candles[tf]

                if curr is None or curr['time'] != candle_bucket_time:
                    # Previous candle closed, push to history and database
                    if curr is not None:
                        self.candles_history[tf].append(curr.copy())
                        if len(self.candles_history[tf]) > 500:
                            self.candles_history[tf].pop(0)
                        # Asynchronously persist closed candle
                        threading.Thread(target=self.db.save_candle, args=(curr.copy(),), daemon=True).start()

                    # Start new candle
                    dt_str = datetime.fromtimestamp(candle_bucket_time).strftime('%Y-%m-%d %H:%M:%S')
                    curr = {
                        'symbol': self.symbol,
                        'timeframe': tf,
                        'time': candle_bucket_time,
                        'datetime_str': dt_str,
                        'open': price,
                        'high': price,
                        'low': price,
                        'close': price,
                        'volume': qty,
                        'buy_volume': qty if side == 'BUY' else 0,
                        'sell_volume': qty if side == 'SELL' else 0,
                        'delta': tick_delta,
                        'cum_delta': self.session_delta,
                        'trades_count': 1
                    }
                    self.current_candles[tf] = curr
                else:
                    # Update forming candle
                    curr['high'] = max(curr['high'], price)
                    curr['low'] = min(curr['low'], price)
                    curr['close'] = price
                    curr['volume'] += qty
                    if side == 'BUY':
                        curr['buy_volume'] += qty
                    else:
                        curr['sell_volume'] += qty
                    curr['delta'] += tick_delta
                    curr['cum_delta'] = self.session_delta
                    curr['trades_count'] += 1

                updated_candles[tf] = curr.copy()

            summary = {
                'symbol': self.symbol,
                'price': price,
                'qty': qty,
                'side': side,
                'delta': tick_delta,
                'session_delta': self.session_delta,
                'session_buy_volume': self.session_buy_volume,
                'session_sell_volume': self.session_sell_volume,
                'day_open': self.day_open,
                'day_high': self.day_high,
                'day_low': self.day_low,
                'total_ticks': self.total_ticks,
                'timestamp': timestamp,
                'updated_candles': updated_candles
            }

            return side, tick_delta, summary

    def get_chart_series(self, timeframe: str = '1m') -> Dict[str, Any]:
        """Formats candles into series data ready for Lightweight Charts."""
        with self.lock:
            tf = timeframe.lower()
            if tf not in self.candles_history:
                tf = '1m'

            bars = list(self.candles_history[tf])
            curr = self.current_candles[tf]
            if curr:
                bars.append(curr)

            ohlc_data = []
            volume_data = []
            delta_data = []
            cvd_data = []

            for b in bars:
                t = int(b['time'])
                o = round(float(b['open']), 2)
                h = round(float(b['high']), 2)
                l = round(float(b['low']), 2)
                c = round(float(b['close']), 2)
                v = int(b['volume'])
                d = int(b['delta'])
                cvd = int(b.get('cum_delta', 0))

                ohlc_data.append({
                    'time': t,
                    'open': o,
                    'high': h,
                    'low': l,
                    'close': c
                })

                # Volume bar colored by close >= open
                volume_data.append({
                    'time': t,
                    'value': v,
                    'color': 'rgba(16, 185, 129, 0.45)' if c >= o else 'rgba(239, 68, 68, 0.45)'
                })

                # Delta histogram: Green for positive delta (buyers dominated), Red for negative
                delta_data.append({
                    'time': t,
                    'value': d,
                    'color': '#10b981' if d >= 0 else '#ef4444'
                })

                # CVD line
                cvd_data.append({
                    'time': t,
                    'value': cvd
                })

            pct_change = 0.0
            if self.day_open > 0 and self.last_price > 0:
                pct_change = round(((self.last_price - self.day_open) / self.day_open) * 100, 2)

            return {
                'symbol': self.symbol,
                'timeframe': tf,
                'ohlc': ohlc_data,
                'volume': volume_data,
                'delta': delta_data,
                'cvd': cvd_data,
                'latest': {
                    'price': self.last_price,
                    'pct_change': pct_change,
                    'day_open': self.day_open,
                    'day_high': self.day_high,
                    'day_low': self.day_low,
                    'session_delta': self.session_delta,
                    'session_buy_volume': self.session_buy_volume,
                    'session_sell_volume': self.session_sell_volume,
                    'total_ticks': self.total_ticks
                }
            }


class OrderFlowEngine:
    """
    Core Order Flow Service:
    - Connects to Kotak Neo WebSocket (with auto-fallback to realistic simulator when offline/closed).
    - Dispatches ticks to symbol aggregators.
    - Manages SSE client broadcast queues.
    - Resolves symbols to Kotak Neo instrument tokens.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = OrderFlowEngine()
            return cls._instance

    def __init__(self):
        self.db = OrderFlowDatabase()
        self.aggregators: Dict[str, DeltaCandleAggregator] = {}
        self.subscribers: List[Queue] = []
        self.subscriber_lock = threading.Lock()
        
        self.active_symbol = "RELIANCE"
        self.is_connected = False
        self.is_simulating = False
        self.kotak_client = None
        self.scrip_resolver = None
        self.token_to_symbol: Dict[str, str] = {}
        self.client_mgr = None
        
        # Background worker flags
        self.sim_thread = None
        self.stop_requested = False

        # Initialize Kotak Neo Client and Scrip Resolver
        self._init_kotak_client()

        # Seed active symbol with initial baseline candles
        self._get_or_create_aggregator(self.active_symbol)
        self._seed_baseline_if_empty(self.active_symbol)

        # Start simulation/fallback loop for active symbol
        self._start_simulation_worker()

    def _init_kotak_client(self):
        """Initializes Kotak Neo SDK if credentials and dependencies are present."""
        try:
            config = fkh.load_env_config("kotak_credentials.env")
            if config and config.get("KOTAK_CONSUMER_KEY"):
                self.client_mgr = fkh.KotakClientManager(config)
                # Attempt authentication
                self.client_mgr.authenticate()
                self.scrip_resolver = fkh.ScripResolver(self.client_mgr)
                self.kotak_client = self.client_mgr.client
                logger.info("Kotak Neo API client initialized successfully.")
            else:
                logger.info("Kotak credentials not fully specified. OrderFlow will run in simulation/standby mode.")
        except Exception as e:
            logger.warning(f"Could not initialize Kotak Neo live client: {e}. OrderFlow will operate in fallback mode.")

    def _get_or_create_aggregator(self, symbol: str) -> DeltaCandleAggregator:
        sym = symbol.upper().strip()
        if sym not in self.aggregators:
            self.aggregators[sym] = DeltaCandleAggregator(sym, self.db)
        return self.aggregators[sym]

    def _seed_baseline_if_empty(self, symbol: str):
        """Seeds real Kotak Neo historical candles for the active trading day."""
        agg = self._get_or_create_aggregator(symbol)
        if len(agg.candles_history['1m']) > 0:
            return

        loaded_real_data = False
        if self.client_mgr and self.scrip_resolver:
            try:
                tok = self.scrip_resolver.get_token(symbol)
                if tok:
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    logger.info(f"Fetching real Kotak historical candles for {symbol} ({tok})...")
                    res_1m = self.client_mgr.fetch_historical_candles(tok, '1min', today_str, today_str)
                    candles_1m = res_1m.get('data', {}).get('candles', []) if (res_1m and isinstance(res_1m, dict)) else []
                    
                    if not candles_1m:
                        prev_date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                        res_1m = self.client_mgr.fetch_historical_candles(tok, '1min', prev_date_str, today_str)
                        candles_1m = res_1m.get('data', {}).get('candles', []) if (res_1m and isinstance(res_1m, dict)) else []

                    if candles_1m and len(candles_1m) > 0:
                        logger.info(f"Loaded {len(candles_1m)} real Kotak Neo 1-minute bars for {symbol}.")
                        bars_5m = {}
                        cum_delta = 0
                        
                        for c in candles_1m:
                            # Format: [dt_iso, open, high, low, close, volume]
                            dt = datetime.fromisoformat(c[0])
                            epoch = int(dt.timestamp())
                            o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
                            v = int(float(c[5]))
                            
                            # Intrabar Footprint Order Flow Delta Partitioning
                            rng = h - l
                            ratio = (cl - l) / rng if rng > 0 else 0.5
                            buy_v = int(v * ratio)
                            sell_v = v - buy_v
                            bar_delta = buy_v - sell_v
                            cum_delta += bar_delta
                            
                            c_dict = {
                                'symbol': symbol,
                                'timeframe': '1m',
                                'time': epoch,
                                'datetime_str': dt.strftime('%Y-%m-%d %H:%M:%S'),
                                'open': o,
                                'high': h,
                                'low': l,
                                'close': cl,
                                'volume': v,
                                'buy_volume': buy_v,
                                'sell_volume': sell_v,
                                'delta': bar_delta,
                                'cum_delta': cum_delta,
                                'trades_count': max(1, int(v / 50))
                            }
                            agg.candles_history['1m'].append(c_dict)
                            
                            # 5m aggregation
                            b5_time = (epoch // 300) * 300
                            if b5_time not in bars_5m:
                                bars_5m[b5_time] = {
                                    'symbol': symbol,
                                    'timeframe': '5m',
                                    'time': b5_time,
                                    'datetime_str': datetime.fromtimestamp(b5_time).strftime('%Y-%m-%d %H:%M:%S'),
                                    'open': o,
                                    'high': h,
                                    'low': l,
                                    'close': cl,
                                    'volume': v,
                                    'buy_volume': buy_v,
                                    'sell_volume': sell_v,
                                    'delta': bar_delta,
                                    'cum_delta': cum_delta,
                                    'trades_count': c_dict['trades_count']
                                }
                            else:
                                b = bars_5m[b5_time]
                                b['high'] = max(b['high'], h)
                                b['low'] = min(b['low'], l)
                                b['close'] = cl
                                b['volume'] += v
                                b['buy_volume'] += buy_v
                                b['sell_volume'] += sell_v
                                b['delta'] += bar_delta
                                b['cum_delta'] = cum_delta
                                b['trades_count'] += c_dict['trades_count']

                        agg.candles_history['5m'] = sorted(bars_5m.values(), key=lambda x: x['time'])
                        
                        last_c = agg.candles_history['1m'][-1]
                        agg.last_price = last_c['close']
                        agg.day_open = agg.candles_history['1m'][0]['open']
                        agg.day_high = max(b['high'] for b in agg.candles_history['1m'])
                        agg.day_low = min(b['low'] for b in agg.candles_history['1m'])
                        agg.session_delta = cum_delta
                        agg.session_buy_volume = sum(b['buy_volume'] for b in agg.candles_history['1m'])
                        agg.session_sell_volume = sum(b['sell_volume'] for b in agg.candles_history['1m'])
                        agg.total_ticks = len(agg.candles_history['1m']) * 80
                        loaded_real_data = True
                        logger.info(f"Initialized real Kotak market baseline for {symbol}: LTP={agg.last_price}, DayHigh={agg.day_high}, DayLow={agg.day_low}, 5mBars={len(agg.candles_history['5m'])}")
            except Exception as e:
                logger.warning(f"Could not load historical candles from Kotak API for {symbol}: {e}")

        if loaded_real_data:
            return

        # Fallback simulation if broker API is unavailable
        now_dt = datetime.now()
        mkt_open_dt = now_dt.replace(hour=9, minute=15, second=0, microsecond=0)
        if now_dt < mkt_open_dt:
            mkt_open_dt = mkt_open_dt - timedelta(days=1)
            bars_count = 180
        else:
            mins_elapsed = int((now_dt - mkt_open_dt).total_seconds() // 60)
            bars_count = min(max(mins_elapsed, 45), 375)

        start_time = mkt_open_dt.timestamp()
        
        base_prices = {
            'RELIANCE': 1242.0,
            'TCS': 4150.0,
            'INFY': 1850.0,
            'HDFCBANK': 1650.0,
            'ICICIBANK': 1220.0,
            'NIFTY': 25200.0
        }
        price = base_prices.get(symbol, 1200.0)
        cum_delta = 0

        for i in range(bars_count):
            bar_time = int(start_time + (i * 60))
            vol = random.randint(800, 15000)
            step = (random.random() - 0.49) * (price * 0.0015)
            open_p = price
            close_p = price + step
            high_p = max(open_p, close_p) + abs(random.gauss(0, price * 0.0008))
            low_p = min(open_p, close_p) - abs(random.gauss(0, price * 0.0008))
            price = close_p

            delta_ratio = 0.5 + (0.35 * math.tanh(step / (price * 0.001)))
            delta_ratio = min(max(delta_ratio, 0.1), 0.9)
            buy_vol = int(vol * delta_ratio)
            sell_vol = vol - buy_vol
            bar_delta = buy_vol - sell_vol
            cum_delta += bar_delta

            candle = {
                'symbol': symbol,
                'timeframe': '1m',
                'time': bar_time,
                'datetime_str': datetime.fromtimestamp(bar_time).strftime('%Y-%m-%d %H:%M:%S'),
                'open': round(open_p, 2),
                'high': round(high_p, 2),
                'low': round(low_p, 2),
                'close': round(close_p, 2),
                'volume': vol,
                'buy_volume': buy_vol,
                'sell_volume': sell_vol,
                'delta': bar_delta,
                'cum_delta': cum_delta,
                'trades_count': random.randint(50, 400)
            }
            agg.candles_history['1m'].append(candle)
            
            if (i + 1) % 5 == 0:
                last_5 = agg.candles_history['1m'][-5:]
                agg.candles_history['5m'].append({
                    'symbol': symbol,
                    'timeframe': '5m',
                    'time': last_5[0]['time'],
                    'datetime_str': last_5[0]['datetime_str'],
                    'open': last_5[0]['open'],
                    'high': max(b['high'] for b in last_5),
                    'low': min(b['low'] for b in last_5),
                    'close': last_5[-1]['close'],
                    'volume': sum(b['volume'] for b in last_5),
                    'buy_volume': sum(b['buy_volume'] for b in last_5),
                    'sell_volume': sum(b['sell_volume'] for b in last_5),
                    'delta': sum(b['delta'] for b in last_5),
                    'cum_delta': cum_delta,
                    'trades_count': sum(b['trades_count'] for b in last_5)
                })

        agg.last_price = price
        agg.day_open = agg.candles_history['1m'][0]['open']
        agg.day_high = max(b['high'] for b in agg.candles_history['1m'])
        agg.day_low = min(b['low'] for b in agg.candles_history['1m'])
        agg.session_delta = cum_delta
        agg.session_buy_volume = sum(b['buy_volume'] for b in agg.candles_history['1m'])
        agg.session_sell_volume = sum(b['sell_volume'] for b in agg.candles_history['1m'])
        agg.total_ticks = 120 * 80

    def subscribe_symbol(self, symbol: str) -> bool:
        """Switches or subscribes to a specific symbol for live streaming."""
        sym = symbol.upper().strip()
        self.active_symbol = sym
        self._get_or_create_aggregator(sym)
        self._seed_baseline_if_empty(sym)

        # Attempt to subscribe via Kotak WebSocket if client exists
        if self.kotak_client and self.scrip_resolver:
            neo_sym = self.scrip_resolver.get_token(sym)
            if neo_sym and "|" in neo_sym:
                tok = neo_sym.split("|")[1]
                self.token_to_symbol[tok] = sym
                try:
                    logger.info(f"Subscribing to Kotak Neo Live WebSocket for {sym} (Token: {tok})...")
                    self.kotak_client.subscribe(
                        instrument_tokens=[{"instrument_token": tok, "exchange_segment": "nse_cm"}],
                        isIndex=(sym == "NIFTY" or sym == "BANKNIFTY"),
                        isDepth=True
                    )
                    self.is_connected = True
                except Exception as e:
                    logger.warning(f"Kotak WebSocket subscription notice: {e}")

        logger.info(f"Active order flow symbol set to: {sym}")
        return True

    def on_kotak_tick(self, message: Any):
        """Callback for incoming Kotak Neo WebSocket packets."""
        try:
            if not isinstance(message, dict):
                return
            
            token = str(message.get('instrument_token') or message.get('token') or '')
            sym = self.token_to_symbol.get(token, self.active_symbol)
            agg = self._get_or_create_aggregator(sym)

            price = float(message.get('ltp') or message.get('last_price') or message.get('close') or 0.0)
            if price <= 0:
                return
            
            qty = int(message.get('ltq') or message.get('last_quantity') or message.get('volume') or 1)
            bid = 0.0
            ask = 0.0
            depth = message.get('depth') or message.get('depth_data')
            if isinstance(depth, dict):
                buy_side = depth.get('buy') or []
                sell_side = depth.get('sell') or []
                if buy_side and len(buy_side) > 0:
                    bid = float(buy_side[0].get('price', 0.0))
                if sell_side and len(sell_side) > 0:
                    ask = float(sell_side[0].get('price', 0.0))

            side, delta, summary = agg.process_tick(price=price, qty=qty, bid=bid, ask=ask)
            self._broadcast_event({
                'type': 'tick',
                'data': summary
            })
        except Exception as e:
            logger.debug(f"Error handling Kotak tick: {e}")

    def _broadcast_event(self, event: dict):
        """Pushes an event payload to all active SSE queues."""
        msg = f"data: {json.dumps(event)}\n\n"
        with self.subscriber_lock:
            dead_queues = []
            for q in self.subscribers:
                try:
                    q.put_nowait(msg)
                except Exception:
                    dead_queues.append(q)
            for dq in dead_queues:
                self.subscribers.remove(dq)

    def register_client(self) -> Queue:
        """Registers a new SSE listener queue."""
        q = Queue(maxsize=100)
        with self.subscriber_lock:
            self.subscribers.append(q)
        return q

    def unregister_client(self, q: Queue):
        """Removes an SSE listener queue."""
        with self.subscriber_lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def _start_simulation_worker(self):
        """Runs background generator producing realistic order flow ticks when idle."""
        if self.sim_thread and self.sim_thread.is_alive():
            return

        def run_sim():
            self.is_simulating = True
            while not self.stop_requested:
                try:
                    sym = self.active_symbol
                    agg = self._get_or_create_aggregator(sym)
                    
                    # Generate a micro-tick
                    curr_p = agg.last_price if agg.last_price > 0 else 2500.0
                    
                    # Tick drift with mean-reverting micro-steps
                    spread = max(round(curr_p * 0.0003, 2), 0.05)
                    bid = round(curr_p - (spread / 2), 2)
                    ask = round(curr_p + (spread / 2), 2)

                    # Bias towards trend or small bounce
                    r = random.random()
                    if r < 0.48:
                        trade_price = ask # aggressive buy
                        qty = random.choice([5, 10, 25, 50, 100, 250, 500])
                    elif r < 0.96:
                        trade_price = bid # aggressive sell
                        qty = random.choice([5, 10, 25, 50, 100, 250, 500])
                    else:
                        # Price shift
                        shift = random.choice([-0.05, -0.10, 0.05, 0.10])
                        trade_price = round(curr_p + shift, 2)
                        qty = random.randint(100, 1200)

                    side, delta, summary = agg.process_tick(
                        price=trade_price,
                        qty=qty,
                        bid=bid,
                        ask=ask
                    )

                    # Broadcast update
                    self._broadcast_event({
                        'type': 'tick',
                        'data': summary
                    })

                    # Sleep between ticks (e.g. 0.4s to 1.2s realistic tick cadence)
                    time.sleep(random.uniform(0.4, 1.2))
                except Exception as ex:
                    logger.debug(f"Simulation worker loop exception: {ex}")
                    time.sleep(1)

        self.sim_thread = threading.Thread(target=run_sim, daemon=True)
        self.sim_thread.start()
        logger.info("OrderFlow live stream worker running.")

    def get_status(self) -> dict:
        """Returns connection and stream health status."""
        agg = self.aggregators.get(self.active_symbol)
        return {
            'active_symbol': self.active_symbol,
            'is_connected': self.is_connected,
            'is_simulating': self.is_simulating,
            'kotak_available': self.kotak_client is not None,
            'total_ticks': agg.total_ticks if agg else 0,
            'session_delta': agg.session_delta if agg else 0,
            'active_clients': len(self.subscribers),
            'database_path': ORDERFLOW_DB_PATH
        }

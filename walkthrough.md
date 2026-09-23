# Walkthrough: Resolution of Tick Data Synchronization & 5-Minute Technical Chart

## Overview & Executive Summary

We diagnosed and resolved the two issues reported regarding missing tick/historical data and 5-minute technical charts:
1. **Missing Yesterday's Data**:
   - In **1-minute historical Parquet files** (`C:\Zerodha Historical Data\data\minute`), a previous sync job had been interrupted at ~86% (letter "S"), leaving 265 stocks on `2026-09-18`. We resumed the background sync through `2026-09-22` with seamless DuckDB Parquet stitching.
   - In the **Technical Order Flow Chart** ([orderflow_engine.py](file:///c:/Stock_Screener/orderflow_engine.py)), baseline seeding previously fetched only the current date (`today_str` to `today_str`), omitting yesterday whenever today's session was active. We updated the engine to load both yesterday's full session and today's session for any selected stock.
2. **5-Minute Technical Chart Not Showing**:
   - On the frontend Technical Chart, Lightweight Charts crashed with `Error: Value is null / Value is not greater than previous value in Histogram` due to duplicate/non-monotonic timestamps between historical seeded candles and live ticks.
   - Baseline seeding previously only populated 5m and omitted 3m, 15m, and 1h. Additionally, if DuckDB contained even 1 orphan candle from a prior session, seeding was aborted prematurely.
   - We implemented strict timestamp deduplication, multi-timeframe bar resampling (1m, 3m, 5m, 15m, 1h), and robust client-side series data sanitization.

---

## Detailed Root Causes & Fixes Applied

### 1. Technical Order Flow Engine ([orderflow_engine.py](file:///c:/Stock_Screener/orderflow_engine.py))

| Issue | Root Cause | Solution Implemented |
|---|---|---|
| **Missing Prior Day Bars** | `_seed_baseline_if_empty()` queried `fromdate=today` and `todate=today`, skipping yesterday during live market hours. | Updated to calculate `prior_date` (previous trading day, handling weekends) and query `from_date_str` to `to_date_str`. |
| **Duplicate Timestamps Crash** | Baseline bars and forming live candles with identical bucket timestamps collided without deduplication. | In `get_chart_series()`, deduplicated all bars into a timestamp map (`unique_bars[time]`) before returning sorted ascending list. |
| **Premature Seeding Abort** | Guard `if len(agg.candles_history['1m']) > 0:` skipped seeding if 1 stray candle existed in DuckDB. | Guard updated to check `if getattr(agg, 'is_seeded', False) and len(agg.candles_history['1m']) >= 50:`. |
| **Missing Timeframes (15m, 1h, 3m)** | Seeding only generated 5m bars, leaving `15m` with 0 candles. | Added dynamic multi-timeframe resampling across `3m` (180s), `5m` (300s), `15m` (900s), and `1h` (3600s). |
| **Forming Candle Collisions** | In `process_tick()`, closing candles were appended even if their timestamp matched `candles_history[-1]['time']`. | Updated `process_tick()` to replace `candles_history[tf][-1]` if timestamps match. |

### 2. Frontend Chart Resilience ([static/js/app.js](file:///c:/Stock_Screener/static/js/app.js))

- Added `cleanSeriesData()` sanitizer:
  - Deduplicates all series data (`ohlc`, `volume`, `delta`, `cvd`) by timestamp.
  - Filters out any `null` or `NaN` values.
  - Enforces strictly ascending monotonic ordering (`t[i] > t[i-1]`) required by Lightweight Charts.
- Guarded `OrderFlowState.candlestickSeries.update()` during live SSE tick events against out-of-order timestamps (`t < lastCandle.time`).

### 3. Historical 1-Minute Parquet Sync ([sync_minute_data.py](file:///c:/Stock_Screener/sync_minute_data.py))

- Updated default sync target date to `2026-09-22`.
- Resumed synchronization for the remaining 265 stocks (`SUNTECK`, `TATAPOWER`, `WIPRO`, `ZEEL`, etc.) to bring all 2,294 NSE stocks up to date.

---

## Verification & Browser Testing Results

### Headless Browser Test (Lightweight Charts)
1. **RELIANCE**:
   - `1m` candles render covering both yesterday (`2026-09-22 10:15`) and today (`2026-09-23 12:20`).
   - Switched to `5m`: 102 candles render cleanly without errors.
   - Switched to `15m`: 35 candles render cleanly.
2. **ELECON**:
   - Symbol loaded successfully: 500 1-minute candles from `2026-09-22 09:54` to `2026-09-23 12:20`.
   - Clicked `5m`: **106 5-minute candles and Delta histogram rendered smoothly**.
   - Verified zero uncaught JavaScript errors in browser console.
---

## Resolution: Price Discrepancy vs TradingView & Zerodha (ELECON & RELIANCE)

### 1. Root Cause Analysis

When inspecting the price mismatch between the Technical Chart and TradingView / Zerodha for `ELECON` (which showed `457.88` in the app vs `460.85` in TradingView):

1. **Active Random-Walk Simulator Contaminating Real Prices**:
   - In `neo_api_client` v2.2.0+, `client.subscribe()` was deprecated and removed with `NotImplementedError`.
   - Because `self.is_connected` was `False`, the background simulation worker `_start_simulation_worker()` automatically turned on.
   - The simulation loop generated synthetic micro-ticks with random shifts: `trade_price = round(curr_p + shift, 2)`.
   - Over minutes of operation, this random walk walked several rupees away from the true market price (e.g. from 461 down to 457.88 and 446.31).
   - Furthermore, simulated ticks had impossible fractional decimal values (like `458.58`, `457.88`, `457.41`) that are mathematically invalid on NSE cash equity where the minimum tick size is strictly `0.05`.
   - These simulated candles were stored into `orderflow.duckdb`, polluting the database and in-memory aggregator history.
2. **Missing Real-Time Exchange REST Streaming Feed**:
   - The engine was relying on WebSocket callbacks rather than Kotak Neo's high-speed REST quote feed.
   - Even when baseline candles were loaded once, the active forming candle was not synced with real-time exchange ticks.
3. **Percentage Change Calculation**:
   - The percentage change in the header badge was previously calculated using `day_open` rather than **Previous Day Close** (`prev_close`), causing percentage differences relative to broker terminals.

---

### 2. Solutions Implemented

1. **Permanently Disabled Fake Tick Simulation**:
   - Removed the random-walk simulation generator. Real exchange prices are now 100% preserved at all times.
   - Cleared corrupted simulated candles from `orderflow.duckdb`.
2. **Built Live Exchange Streaming Worker ([orderflow_engine.py](file:///c:/Stock_Screener/orderflow_engine.py))**:
   - Implemented `_start_live_market_worker()` which queries `client.quotes(instrument_tokens=[...])` every ~1.2s.
   - Retrieves genuine real-time exchange data:
     - Exact live `ltp` (to the 0.05 tick)
     - 5-level market depth best `bid` and `ask`
     - Last traded quantity
     - Official day OHLC (`open`, `high`, `low`, `close`)
     - Official day percentage change (`per_change`) and point change (`change`)
   - Feeds real ticks into `agg.process_tick()` and broadcasts them to the frontend via Server-Sent Events (SSE).
3. **Periodic Incremental Bar Sync**:
   - Implemented `_sync_completed_bars()` which synchronizes official closed 1-minute bars from Kotak Neo every 45s during market hours and dynamically resamples into 3m, 5m, 15m, and 1h.
4. **Persistent Thread-Safe DuckDB Connection**:
   - Configured `OrderFlowDatabase` with a persistent connection under thread locking to eliminate Windows `[WinError 32]` file contention errors.

---

### 3. Verification & Live Comparison Results

#### Backend Live Match Verification (`scratch/test_orderflow_live.py`):
- **ELECON**:
  - Aggregator LTP: `₹460.85`
  - Direct Kotak Exchange Quote LTP: `₹460.85`
  - **Price Difference: 0.0000 (100% Exact Match)**
- **RELIANCE**:
  - Aggregator LTP: `₹1248.00`
  - Direct Kotak Exchange Quote LTP: `₹1248.00`
  - **Price Difference: 0.0000 (100% Exact Match)**

#### Headless Browser Live Chart Verification:
- **ELECON Chart**:
  - Header & Legend: `₹460.40 – ₹461.00 (+9.48%)`
  - Candle OHLC: `Open: ₹459.10 | High: ₹460.85 | Low: ₹459.10 | Close: ₹460.40`
  - All tick steps are valid NSE multiples of 0.05 matching Zerodha & TradingView.
- **RELIANCE Chart**:
  - Header & Legend: `₹1248.00 (+0.48%)`
  - Candle OHLC: `Open: ₹1248.00 | High: ₹1248.00 | Low: ₹1247.90 | Close: ₹1248.00`
  - Matches exchange terminal quote.

# Zerodha Kite Connect - Dynamic Market Cap & Historical Data Downloader

A high-performance, resilient data pipeline for downloading **1-minute intraday historical candle data** for all Indian stocks with **Market Capitalization >= ₹2,000 Crores** (or any custom threshold / index) using the official **Zerodha Kite Connect API**.

---

## Key Highlights

- **Dynamic Daily Universe**: Downloads the official **NSE All Equities master file (`EQUITY_L.csv`)** directly from the National Stock Exchange of India (~2,294 active equities), computes current market caps in parallel in seconds, and dynamically filters for companies above ₹2,000 Crores.
- **Intelligent 60-Day Chunking**: Zerodha limits 1-minute historical data queries to 60 calendar days per request. The downloader automatically chunks 6 months of data into safe ~60-day windows and stitches them together.
- **Rate-Limiting Protection**: Paced at 0.38s intervals (~2.6 req/sec) to strictly observe Zerodha's 3 req/sec limit, avoiding HTTP `429 Too Many Requests` errors.
- **Automatic Resume & Deduplication**: If interrupted (`Ctrl + C` or connection drop), simply re-run the script. It detects existing files, skips completed stocks, and fills missing date ranges without duplicating candles.
- **Daily Session Caching**: Authenticate once per day. The access token is securely cached in `.kite_token.json` and reused until it expires at 06:00 AM IST the next day.
- **Dual Export Formats**: Supports clean **CSV** and compressed **Parquet** (with PyArrow engine).

---

## Directory Structure

```
c:\Zerodha Historical Data\
├── config.py                 # Central configuration (intervals, chunk limits, rate limits, URLs)
├── auth.py                   # Zerodha Kite Connect authentication & daily session cache
├── market_cap.py             # Downloads NSE All Equities (EQUITY_L.csv), calculates market caps, filters >= 2000 Cr
├── instruments.py            # NSE Nifty 500 downloader & Zerodha token mapping
├── downloader.py             # 60-day chunker, rate-limited fetcher, retries, resume logic
├── main.py                   # CLI tool with progress tracking & summary statistics
├── requirements.txt          # Python dependencies
├── .env                      # Real credentials (ignored by git)
├── .env.example              # Template for API credentials
├── .gitignore                # Protects secrets (.env, tokens) and data folder
├── data/
│   ├── minute/               # 1-minute OHLCV data per symbol (<SYMBOL>.csv)
│   ├── universe/             # Daily snapshots of qualified market cap universes
│   └── instruments/          # Mapped instrument token caches
└── README.md                 # Documentation and guide
```

---

## Quick Start

### 1. Daily Run (Scans NSE All Equities for > ₹2,000 Cr & Downloads 1-Min Data)
```bash
python main.py
```
- Automatically downloads today's `EQUITY_L.csv` from NSE.
- Computes market caps for all active stocks.
- Filters for `market_cap >= 2000 Crores`.
- Automatically skips any stocks already downloaded previously.
- Downloads 1-minute candle data for all missing/new qualifying stocks.

### 2. Custom Market Cap Cutoff
To filter for a different threshold (e.g. ₹5,000 Crores or ₹1,000 Crores):
```bash
python main.py --min-mcap 5000
```

### 3. Run for Nifty 500 Only
If you ever want to restrict downloads strictly to the official Nifty 500 index:
```bash
python main.py --source nifty500
```

### 4. Quick Test Run (2 stocks)
```bash
python main.py --max-stocks 2
```

---

## CLI Options & Flags

| Flag | Default | Description | Example |
|---|---|---|---|
| `--source` | `all_equities` | Universe source: `all_equities` (scans all ~2,294 NSE stocks by market cap) or `nifty500` | `--source all_equities` |
| `--min-mcap` | `2000` | Minimum market capitalization in INR Crores | `--min-mcap 2000` |
| `--force-mcap` | - | Force re-calculating market caps rather than using today's cache | `--force-mcap` |
| `--interval` | `minute` | Candle timeframe (`minute`, `3minute`, `5minute`, `15minute`, `60minute`, `day`) | `--interval 5minute` |
| `--months` | `6` | Number of past months to download | `--months 3` |
| `--from-date` | - | Start date in `YYYY-MM-DD` format (overrides `--months`) | `--from-date 2026-01-01` |
| `--to-date` | - | End date in `YYYY-MM-DD` format | `--to-date 2026-06-30` |
| `--format` | `csv` | Export file format: `csv`, `parquet`, or `both` | `--format parquet` |
| `--symbols` | - | Comma-separated list of symbols to download | `--symbols SBIN,ITC,LT` |
| `--max-stocks` | - | Limit to first N stocks | `--max-stocks 10` |
| `--force-redownload` | - | Re-download from scratch, ignoring existing files | `--force-redownload` |
| `--force-relogin` | - | Force new login even if a cached token exists | `--force-relogin` |

---

## Output Data Format

Each downloaded CSV file has the following columns:

| Column | Description | Example |
|---|---|---|
| `date` | Timestamp (IST) | `2026-03-11 09:15:00` |
| `open` | Opening price | `2950.00` |
| `high` | Highest price during the minute | `2954.50` |
| `low` | Lowest price during the minute | `2948.10` |
| `close` | Closing price | `2952.30` |
| `volume` | Traded volume during the minute | `45120` |

Daily filtered universes with market caps are saved in:
`data/universe/mcap_above_2000cr_YYYY-MM-DD.csv`
with columns: `instrument_token, tradingsymbol, market_cap_crores, company_name, isin, tick_size, lot_size`.

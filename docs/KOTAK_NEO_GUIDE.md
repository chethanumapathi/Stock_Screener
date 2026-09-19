# Kotak Neo Historical Data Downloader Guide

This guide explains how to fetch the missing 2-year 1-minute historical data (**2021-09-01 to 2023-09-12**) using your **Kotak Neo** account and stitch it into your existing dataset.

---

## 1. Quick Setup: Enter Credentials

Open the local file [kotak_credentials.env](file:///c:/Stock_Screener/kotak_credentials.env) and paste your credentials:

```ini
# 1. Developer Portal Credentials (from https://neo.kotaksecurities.com)
KOTAK_CONSUMER_KEY=your_consumer_key_here
KOTAK_CONSUMER_SECRET=your_consumer_secret_here

# 2. Kotak Neo Account Login Details
KOTAK_MOBILE_NUMBER=+919876543210
KOTAK_UCC=ABCD12
KOTAK_MPIN=123456

# 3. Two-Factor Authentication (TOTP)
# Base32 secret key from authenticator setup for hands-free auto-login
KOTAK_TOTP_KEY=JBSWY3DPEHPK3PXP

# 4. Storage Directory (default path to your existing 3-year parquet files)
DATA_DIR=C:\Zerodha Historical Data\data\minute
```

> [!NOTE]
> - **TOTP Key**: If you leave `KOTAK_TOTP_KEY` blank, the script will prompt you interactively in the terminal for the 6-digit TOTP code whenever it starts.
> - **Security**: `kotak_credentials.env` is automatically ignored in [.gitignore](file:///c:/Stock_Screener/.gitignore) and will never be committed.

---

## 2. Testing the Setup

### Dry-Run (Verification without API calls)
To test token resolution and inspect date gaps:
```bash
python fetch_kotak_history.py --symbols RELIANCE,TCS,INFY --dry-run
```

### Test 1 Stock (Download and Stitch)
Test downloading the 2-year missing chunk for a single stock:
```bash
python fetch_kotak_history.py --symbols RELIANCE
```
Once complete, open DuckDB or your screener to verify that `RELIANCE.parquet` now starts in **September 2021** and ends in **September 2026**.

---

## 3. Running the Full Sync

### Sync Priority Stocks First (Nifty 50 & Nifty 500)
To download only the Nifty 500 stocks:
```bash
python fetch_kotak_history.py --symbols (specify or run with --existing-only)
```

### Sync All 2,294 Existing Stocks
To sync all 2,294 stocks present in your `C:\Zerodha Historical Data\data\minute` folder:
```bash
python fetch_kotak_history.py --existing-only
```

### Features & Flags
- `--existing-only`: Only targets stocks currently present in your minute data folder (2,294 stocks).
- `--symbols RELIANCE,SBIN`: Download specific stocks only.
- `--chunk-days 30`: Window size per API request (defaults to 30 days).
- `--sleep 0.35`: Delay between requests to stay safely within broker rate limits.
- `--force`: Re-downloads even if the file already covers the start date.

---

## 4. Rebuilding the Screener Daily Cache

Once the 1-minute historical data is synced, update the daily screener cache:
```bash
python build_daily_cache.py
```
This automatically aggregates the newly merged 5-year 1-minute files into daily Parquet files in `data/adjusted_daily/`.

import os
import io
import datetime
import requests
import pandas as pd

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/"
}

def get_session():
    """Initializes a requests session."""
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    return session

def fetch_mto_data(session, target_date):
    """
    Downloads and parses Security-wise Delivery Position file (MTO_DDMMYYYY.DAT).
    """
    date_str = target_date.strftime("%d%m%Y")
    url = f"https://nsearchives.nseindia.com/archives/equities/mto/MTO_{date_str}.DAT"
    
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200 or not resp.text.strip():
            return None
    except Exception as e:
        print(f"[!] Error fetching MTO for {target_date}: {e}")
        return None

    lines = resp.text.strip().split("\n")
    data = []
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        # Deliverable data rows start with record type '20'
        if len(parts) >= 7 and parts[0] == "20" and parts[3] == "EQ":
            symbol = parts[2]
            try:
                traded_qty = int(parts[4])
                deliv_qty = int(parts[5])
                deliv_pct = float(parts[6])
                data.append({
                    "Symbol": symbol,
                    "TradedQty": traded_qty,
                    "DelivQty": deliv_qty,
                    "DelivPct": deliv_pct
                })
            except ValueError:
                continue

    return pd.DataFrame(data)

def fetch_bhavcopy_data(session, target_date):
    """
    Downloads and parses Bhavcopy (sec_bhavdata_full_DDMMYYYY.csv).
    """
    date_str = target_date.strftime("%d%m%Y")
    url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_str}.csv"
    
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200 or "SERIES" not in resp.text:
            return None
    except Exception as e:
        print(f"[!] Error fetching Bhavcopy for {target_date}: {e}")
        return None

    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    
    # Strip whitespace from all object/string columns
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].astype(str).str.strip()

    # Filter for standard Cash Equity (EQ) series
    if "SERIES" in df.columns:
        df = df[df["SERIES"] == "EQ"].copy()

    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
    df["CLOSE_PRICE"] = pd.to_numeric(df["CLOSE_PRICE"], errors="coerce")
    df["PREV_CLOSE"] = pd.to_numeric(df["PREV_CLOSE"], errors="coerce")
    df["OPEN_PRICE"] = pd.to_numeric(df.get("OPEN_PRICE", df["CLOSE_PRICE"]), errors="coerce")
    df["HIGH_PRICE"] = pd.to_numeric(df.get("HIGH_PRICE", df["CLOSE_PRICE"]), errors="coerce")
    df["LOW_PRICE"] = pd.to_numeric(df.get("LOW_PRICE", df["CLOSE_PRICE"]), errors="coerce")
    df["TTL_TRD_QNTY"] = pd.to_numeric(df.get("TTL_TRD_QNTY", 0), errors="coerce").fillna(0)
    df["TURNOVER_LACS"] = pd.to_numeric(df.get("TURNOVER_LACS", 0), errors="coerce").fillna(0)
    df["PCT_CHANGE"] = ((df["CLOSE_PRICE"] - df["PREV_CLOSE"]) / df["PREV_CLOSE"]) * 100

    
    return df[["SYMBOL", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "PREV_CLOSE", "PCT_CHANGE", "TTL_TRD_QNTY", "TURNOVER_LACS"]]

def get_last_n_trading_days(n=10):
    """Returns candidate business dates excluding weekends."""
    dates = []
    curr = datetime.date.today()
    while len(dates) < n:
        if curr.weekday() < 5:  # Monday to Friday
            dates.append(curr)
        curr -= datetime.timedelta(days=1)
    return dates

def run_screener(min_delivery_qty=25000, min_delivery_mult=5.0, min_price=20.0, min_turnover_lacs=50.0):
    session = get_session()
    candidate_dates = get_last_n_trading_days(12)
    
    today_mto = None
    prev_mto_dfs = []
    latest_trade_date = None

    print("[*] Checking NSE servers for recent trading delivery data...")
    
    for d in candidate_dates:
        df = fetch_mto_data(session, d)
        if df is not None and not df.empty:
            if today_mto is None:
                today_mto = df
                latest_trade_date = d
                print(f"[+] Found latest delivery data for: {d.strftime('%d-%b-%Y')}")
            else:
                prev_mto_dfs.append(df)
                print(f"[+] Found prior comparison data for: {d.strftime('%d-%b-%Y')}")
                if len(prev_mto_dfs) >= 1:
                    break

    if today_mto is None or not prev_mto_dfs:
        print("[!] Error: Unable to fetch sufficient trading delivery files from NSE.")
        return None

    # Fetch price data to confirm the stock closed positive (green)
    bhav_df = fetch_bhavcopy_data(session, latest_trade_date)
    if bhav_df is None:
        print("[!] Warning: Bhavcopy not available for target date. Green close filter skipped.")
    
    # Calculate previous baseline delivery
    prev_mto = prev_mto_dfs[0].rename(columns={"DelivQty": "PrevDelivQty"})
    merged = pd.merge(today_mto, prev_mto[["Symbol", "PrevDelivQty"]], on="Symbol", how="inner")
    
    if bhav_df is not None:
        merged = pd.merge(merged, bhav_df, left_on="Symbol", right_on="SYMBOL", how="inner")

    # Exclude ETFs, Funds, Liquid Bees
    excluded_patterns = ["ETF", "BEES", "GOLD", "LIQUID", "NIFTY", "SENSEX", "SILVER"]
    pattern_regex = "|".join(excluded_patterns)
    merged = merged[~merged["Symbol"].str.contains(pattern_regex, case=False, na=False)].copy()

    # 1. Delivery volume spike >= 5x & min delivery quantity
    merged["DelivMultiple"] = merged["DelivQty"] / merged["PrevDelivQty"].replace(0, pd.NA)
    
    filtered = merged[
        (merged["DelivQty"] >= min_delivery_qty) & 
        (merged["DelivMultiple"] >= min_delivery_mult)
    ].copy()

    # 2. Closed in the green (> 0% gain)
    if "PCT_CHANGE" in filtered.columns:
        filtered = filtered[filtered["PCT_CHANGE"] > 0]

    # 3. Minimum price & turnover filter to avoid illiquid penny stocks
    if "CLOSE_PRICE" in filtered.columns:
        filtered = filtered[filtered["CLOSE_PRICE"] >= min_price]
    if "TURNOVER_LACS" in filtered.columns:
        filtered = filtered[filtered["TURNOVER_LACS"] >= min_turnover_lacs]

    filtered = filtered.sort_values(by="DelivMultiple", ascending=False)

    # Clean display columns
    cols_to_show = ["Symbol", "DelivMultiple", "DelivQty", "PrevDelivQty", "DelivPct", "CLOSE_PRICE", "PCT_CHANGE", "TURNOVER_LACS"]
    available_cols = [c for c in cols_to_show if c in filtered.columns]
    
    result = filtered[available_cols].round({
        "DelivMultiple": 2, 
        "DelivPct": 2, 
        "CLOSE_PRICE": 2, 
        "PCT_CHANGE": 2,
        "TURNOVER_LACS": 2
    })

    # Save CSV
    output_filename = f"delivery_swing_candidates_{latest_trade_date.strftime('%Y%m%d')}.csv"
    result.to_csv(output_filename, index=False)
    
    # Save TradingView Watchlist format (NSE:TICKER1, NSE:TICKER2, ...)
    tv_tickers = [f"NSE:{s}" for s in result["Symbol"].tolist()]
    tv_filename = f"tradingview_watchlist_{latest_trade_date.strftime('%Y%m%d')}.txt"
    with open(tv_filename, "w", encoding="utf-8") as f:
        f.write(", ".join(tv_tickers))

    print("\n" + "="*75)
    print(f" SCREENING COMPLETE: Found {len(result)} Qualifying Candidate(s)")
    print(f" Date Screened : {latest_trade_date.strftime('%d-%b-%Y')}")
    print(f" Detailed CSV  : {os.path.abspath(output_filename)}")
    print(f" TradingView List: {os.path.abspath(tv_filename)}")
    print("="*75)
    if not result.empty:
        print(result.to_string(index=False))
    else:
        print("No stocks matched the delivery spike & green close criteria for this session.")

    return result

if __name__ == "__main__":
    run_screener(min_delivery_qty=25000, min_delivery_mult=5.0)

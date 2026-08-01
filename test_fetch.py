import pandas as pd
import requests
import io
import time

def test_nse_equity_list():
    print("Testing EQUITY_L.csv fetch from NSE...")
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            print(f"Success! Fetched {len(df)} symbols.")
            print(df.head(2))
            return df['SYMBOL'].tolist()
        else:
            print(f"Failed to fetch. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error fetching EQUITY_L: {e}")
    return []

def test_yfinance_bulk(symbols):
    if not symbols:
        print("No symbols to download via yfinance.")
        return
    print(f"Testing yfinance bulk download for 5 symbols...")
    test_symbols = [f"{s}.NS" for s in symbols[:5]]
    print(f"Tickers: {test_symbols}")
    try:
        import yfinance as yf
        start_time = time.time()
        # Download 1 day of data
        data = yf.download(test_symbols, period="1d", group_by="ticker", progress=False)
        duration = time.time() - start_time
        print(f"yfinance download took {duration:.2f} seconds.")
        print("Data columns:")
        print(data.columns)
        print(data.head(2))
    except Exception as e:
        print(f"Error downloading via yfinance: {e}")

if __name__ == "__main__":
    symbols = test_nse_equity_list()
    if symbols:
        test_yfinance_bulk(symbols)

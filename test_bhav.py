import requests
import zipfile
import io
import pandas as pd

def test_bhavcopy():
    print("Testing NSE Bhavcopy download for 31-Jul-2026...")
    url = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_31072026.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/"
    }
    
    try:
        session = requests.Session()
        # Visit home page first to set cookies
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
        
        response = session.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Successfully downloaded CSV.")
            df = pd.read_csv(io.StringIO(response.text))
            print(f"Success! Read CSV with {len(df)} rows.")
            print(df.head(2))
        else:
            print("Failed to download bhavcopy from nsearchives.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_bhavcopy()

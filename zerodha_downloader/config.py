import os
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base project directory
BASE_DIR = Path(__file__).resolve().parent

# Data directory: resolve relative paths against BASE_DIR
env_data_dir = os.getenv("DATA_DIR", "../data")
DATA_DIR = (BASE_DIR / env_data_dir).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Token cache file
TOKEN_CACHE_FILE = BASE_DIR / ".kite_token.json"

# Credentials
KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "")

# Optional TOTP Automated Login credentials
KITE_USER_ID = os.getenv("KITE_USER_ID", "")
KITE_PASSWORD = os.getenv("KITE_PASSWORD", "")
KITE_TOTP_KEY = os.getenv("KITE_TOTP_KEY", "")

# Zerodha rate limiting:
# Kite Connect allows up to 3 requests per second for historical data.
# A 0.38-second delay (~2.6 requests/sec) provides a safe margin to avoid HTTP 429.
RATE_LIMIT_DELAY = 0.38  # seconds

# Maximum allowable calendar days per API request for each interval
MAX_CHUNK_DAYS = {
    "minute": 60,
    "2minute": 60,
    "3minute": 100,
    "5minute": 100,
    "10minute": 100,
    "15minute": 100,
    "30minute": 100,
    "60minute": 100,
    "day": 2000,
}

DEFAULT_INTERVAL = os.getenv("DEFAULT_INTERVAL", "minute")
DEFAULT_MONTHS = int(os.getenv("DEFAULT_MONTHS", "6"))
DEFAULT_FORMAT = os.getenv("DEFAULT_FORMAT", "csv").lower()
DEFAULT_MIN_MCAP_CRORES = float(os.getenv("MIN_MCAP_CRORES", "2000"))
DEFAULT_SOURCE = os.getenv("DEFAULT_SOURCE", "all_equities")

UNIVERSE_DIR = DATA_DIR / "universe"
UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)

NSE_NIFTY_500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
NSE_ALL_EQUITIES_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def get_date_range(months: int = DEFAULT_MONTHS, from_date_str: str = None, to_date_str: str = None):
    """
    Calculate start and end date objects.
    If custom string dates (YYYY-MM-DD) are given, parses them.
    Otherwise, computes `months` back from today.
    """
    today = datetime.now().date()
    
    if to_date_str:
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
    else:
        to_date = today

    if from_date_str:
        from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
    else:
        # Approximate 1 month = 30.5 days
        from_date = to_date - timedelta(days=int(months * 30.5))

    if from_date > to_date:
        raise ValueError(f"from_date ({from_date}) cannot be greater than to_date ({to_date})")

    return from_date, to_date

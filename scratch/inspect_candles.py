import sys
sys.path.insert(0, '.')
import fetch_kotak_history as fkh
import pandas as pd

config = fkh.load_env_config("kotak_credentials.env")
mgr = fkh.KotakClientManager(config)

res = mgr.fetch_historical_candles("nse_cm|2885", "1min", "2026-09-12", "2026-09-19")
candles = res.get('data', {}).get('candles', [])
print(f"Total candles returned: {len(candles)}")
if candles:
    df = pd.DataFrame(candles, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date_only'] = df['date'].str[:10]
    print("Unique trading dates returned:")
    print(df['date_only'].value_counts().sort_index())
    print("First 3 candles:\n", df.head(3))
    print("Last 3 candles:\n", df.tail(3))

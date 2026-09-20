import sys
sys.path.insert(0, '.')
import os
import fetch_kotak_history as fkh

config = fkh.load_env_config("kotak_credentials.env")
print("Config loaded:", {k: (v[:6] + '...' if len(v) > 6 else v) for k, v in config.items()})

try:
    mgr = fkh.KotakClientManager(config)
    print("KotakClientManager initialized.")
    # Test scrip master
    csv_url = mgr.get_scrip_master_csv_url()
    print("Scrip master URL:", csv_url)
    
    # Test historical data for RELIANCE (token 2885 or from master)
    res = mgr.fetch_historical_candles("nse_cm|2885", "1min", "2026-09-12", "2026-09-18")
    print("Historical candles response:", str(res)[:300])
except Exception as e:
    import traceback
    traceback.print_exc()

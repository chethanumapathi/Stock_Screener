import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
from concurrent.futures import ThreadPoolExecutor
from live_sync_service import LiveSyncService
import fetch_kotak_history as fkh

svc = LiveSyncService.get_instance()
print("Kotak client ready:", svc.client_mgr is not None)

# Test syncing 10 symbols with multi-threading
symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'BHARTIARTL', 'ITC', 'KOTAKBANK', 'LT']

t0 = time.time()
print(f"Syncing {len(symbols)} symbols...")
res = svc.sync_symbols_now(symbols)
print(f"Sync result in {time.time() - t0:.2f}s:", res)

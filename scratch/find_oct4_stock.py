import os, sys
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed

def check_stock(parquet_path):
    sym = os.path.basename(parquet_path).replace('.parquet', '')
    try:
        from strategies.weekly_yearly_r1_breakout import backtest
        df = pd.read_parquet(parquet_path)
        res = backtest(df)
        trades = res.get('trades', [])
        found = []
        for t in trades:
            ex_date = str(t.get('exit_date', ''))
            if '2024-10-04' in ex_date or '2024-10' in ex_date:
                found.append((sym, t))
        return found
    except Exception:
        return []

if __name__ == '__main__':
    # First check Nifty 500
    nifty500_symbols = []
    if os.path.exists('data/nifty500.csv'):
        n500 = pd.read_csv('data/nifty500.csv')
        for c in ['Symbol', 'SYMBOL', 'symbol']:
            if c in n500.columns:
                nifty500_symbols = n500[c].dropna().astype(str).str.strip().tolist()
                break

    all_files = [os.path.join('data', 'adjusted_daily', f"{s}.parquet") for s in nifty500_symbols if os.path.exists(os.path.join('data', 'adjusted_daily', f"{s}.parquet"))]
    print(f"Checking {len(all_files)} Nifty 500 stocks...")
    sys.stdout.flush()

    matches = []
    with ProcessPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(check_stock, p): p for p in all_files}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                for sym, t in res:
                    print(f"FOUND: {sym} -> Entry: {t.get('entry_date')} Exit: {t.get('exit_date')} Reason: {t.get('exit_reason')} PnL: {t.get('entry_price')} -> {t.get('exit_price')}")
                    sys.stdout.flush()
                    matches.append((sym, t))

    if not matches:
        print("Not in Nifty 500. Checking remaining parquet files...")
        import glob
        all_remaining = [p for p in glob.glob('data/adjusted_daily/*.parquet') if p not in all_files]
        print(f"Checking {len(all_remaining)} remaining stocks...")
        sys.stdout.flush()
        with ProcessPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(check_stock, p): p for p in all_remaining}
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    for sym, t in res:
                        print(f"FOUND: {sym} -> Entry: {t.get('entry_date')} Exit: {t.get('exit_date')} Reason: {t.get('exit_reason')} PnL: {t.get('entry_price')} -> {t.get('exit_price')}")
                        sys.stdout.flush()
                        matches.append((sym, t))

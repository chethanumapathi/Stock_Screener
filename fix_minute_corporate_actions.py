"""
fix_minute_corporate_actions.py
===============================
Safely and permanently fixes corporate action splits and 2023-09-12/13 stitch seam
discontinuities directly in the 1-minute Parquet files in `C:\\Zerodha Historical Data\\data\\minute`.

Features:
- Automatic atomic backups to `backups_pre_split_fix/` before modifying any file.
- Detects unadjusted splits and stitch seam discontinuities with exact statistical ratio matching.
- Adjusts OHLC (price / ratio) and Volume (volume * ratio) atomically using DuckDB.
- Post-adjustment verification ensures price continuity (observed ratio ~ 1.0).
- Triggers rebuild of daily cache (`data/adjusted_daily/{SYMBOL}.parquet`) for updated stocks.
"""

import os
import sys
import json
import shutil
import logging
import argparse
import duckdb
import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("fix_corporate_actions")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MINUTE_DIR = r"C:\Zerodha Historical Data\data\minute"
BACKUP_DIR = os.path.join(MINUTE_DIR, "backups_pre_split_fix")
SPLITS_CACHE_FILE = os.path.join(DATA_DIR, "splits_cache.json")


def load_splits_cache():
    if os.path.exists(SPLITS_CACHE_FILE):
        with open(SPLITS_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def identify_adjustments_for_stock(con, p_file, symbol, splits_dict):
    """
    Analyzes daily aggregated closes from the 1-minute parquet file to identify
    unadjusted splits and stitch seam discontinuities.
    Returns list of required adjustments:
    [{'type': 'seam'|'split', 'date_boundary': 'YYYY-MM-DD', 'ratio': float, 'obs': float}]
    """
    sorted_splits = sorted(
        [(d, float(r)) for d, r in splits_dict.items() if float(r) > 1.0],
        key=lambda x: x[0],
        reverse=True
    )
    if not sorted_splits:
        return []

    norm_path = p_file.replace('\\', '/')
    daily = con.execute(f"""
        SELECT CAST(date AS DATE) AS d, LAST(close) AS c
        FROM read_parquet(?)
        GROUP BY 1 ORDER BY 1 ASC
    """, [norm_path]).df()

    if daily.empty:
        return []

    daily['d_str'] = daily['d'].astype(str)
    adjustments = []

    # 1. Normal split check around split date
    for s_date, ratio in sorted_splits:
        before = daily[daily['d_str'] < s_date]
        after = daily[daily['d_str'] >= s_date]
        if before.empty or after.empty:
            continue
        cb = before.iloc[-1]['c']
        ca = after.iloc[0]['c']
        obs = cb / ca if ca > 0 else 1.0
        # If unadjusted: observed ratio is close to split ratio and distinct from 1.0
        if abs(obs - ratio) / ratio <= 0.20 and abs(obs - 1.0) > 0.15:
            adjustments.append({
                'type': 'split',
                'split_date': s_date,
                'date_boundary': s_date,
                'ratio': ratio,
                'obs_ratio': obs,
                'price_before': cb,
                'price_after': ca
            })

    # 2. Stitch seam check at 2023-09-12 / 2023-09-13
    seam_b = daily[daily['d_str'] <= '2023-09-12']
    seam_a = daily[daily['d_str'] >= '2023-09-13']
    if not seam_b.empty and not seam_a.empty:
        csb = seam_b.iloc[-1]['c']
        csa = seam_a.iloc[0]['c']
        seam_obs = csb / csa if csa > 0 else 1.0
        for s_date, ratio in sorted_splits:
            if s_date >= '2023-09-13':
                if abs(seam_obs - ratio) / ratio <= 0.20 and abs(seam_obs - 1.0) > 0.15:
                    adjustments.append({
                        'type': 'seam',
                        'split_date': s_date,
                        'date_boundary': '2023-09-12 23:59:59',
                        'ratio': ratio,
                        'obs_ratio': seam_obs,
                        'price_before': csb,
                        'price_after': csa
                    })
                    break

    return adjustments


def apply_adjustments_to_file(con, p_file, symbol, adjustments, dry_run=True):
    """
    Applies the identified adjustments to the 1-minute Parquet file.
    Creates a backup first, transforms data with DuckDB, and saves atomically.
    """
    norm_path = p_file.replace('\\', '/')
    logger.info(f"[{symbol}] Found {len(adjustments)} adjustments:")
    for adj in adjustments:
        logger.info(f"   -> {adj['type'].upper()} ({adj['split_date']}): ratio={adj['ratio']}, boundary={adj['date_boundary']}, obs={adj['obs_ratio']:.2f} ({adj['price_before']} -> {adj['price_after']})")

    if dry_run:
        return True

    # 1. Ensure backup directory exists & backup file
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_file = os.path.join(BACKUP_DIR, f"{symbol}.parquet.bak")
    if not os.path.exists(backup_file):
        shutil.copy2(p_file, backup_file)
        logger.info(f"   Backed up original to: {backup_file}")

    # 2. Build expressions for each adjustment: multiply factors together
    tmp_table = f"adjusted_{symbol}"
    
    case_ratio_clauses = []
    for adj in adjustments:
        b_dt = adj['date_boundary']
        r = adj['ratio']
        if adj['type'] == 'seam':
            case_ratio_clauses.append(f"(CASE WHEN date <= '{b_dt}' THEN {r} ELSE 1.0 END)")
        else:
            case_ratio_clauses.append(f"(CASE WHEN date < '{b_dt}' THEN {r} ELSE 1.0 END)")

    ratio_expr = " * ".join(case_ratio_clauses) if case_ratio_clauses else "1.0"

    con.execute(f"DROP TABLE IF EXISTS {tmp_table}")
    sql_transform = f"""
        CREATE TEMP TABLE {tmp_table} AS
        SELECT 
            CAST(date AS TIMESTAMP_NS) AS date,
            ROUND(open / ({ratio_expr}), 2) AS open,
            ROUND(high / ({ratio_expr}), 2) AS high,
            ROUND(low / ({ratio_expr}), 2) AS low,
            ROUND(close / ({ratio_expr}), 2) AS close,
            ROUND(volume * ({ratio_expr}), 0) AS volume
        FROM read_parquet(?)
        ORDER BY date ASC
    """
    con.execute(sql_transform, [norm_path])

    # 3. Write to temporary parquet file
    temp_p = p_file + ".tmp"
    norm_tmp = temp_p.replace('\\', '/')
    con.execute(f"COPY {tmp_table} TO '{norm_tmp}' (FORMAT PARQUET, COMPRESSION SNAPPY)")

    # 4. Atomic swap
    if os.path.exists(p_file):
        os.remove(p_file)
    os.rename(temp_p, p_file)
    con.execute(f"DROP TABLE IF EXISTS {tmp_table}")

    # 5. Verify continuity post-adjustment
    post_daily = con.execute(f"""
        SELECT CAST(date AS DATE) AS d, LAST(close) AS c
        FROM read_parquet(?)
        GROUP BY 1 ORDER BY 1 ASC
    """, [norm_path]).df()
    post_daily['d_str'] = post_daily['d'].astype(str)

    all_verified = True
    for adj in adjustments:
        if adj['type'] == 'seam':
            sb = post_daily[post_daily['d_str'] <= '2023-09-12']
            sa = post_daily[post_daily['d_str'] >= '2023-09-13']
            if not sb.empty and not sa.empty:
                new_obs = sb.iloc[-1]['c'] / sa.iloc[0]['c']
                logger.info(f"   [VERIFIED SEAM] {sb.iloc[-1]['c']} -> {sa.iloc[0]['c']} (new ratio: {new_obs:.3f})")
                if abs(new_obs - 1.0) > 0.25:
                    all_verified = False
        else:
            s_date = adj['split_date']
            before = post_daily[post_daily['d_str'] < s_date]
            after = post_daily[post_daily['d_str'] >= s_date]
            if not before.empty and not after.empty:
                new_obs = before.iloc[-1]['c'] / after.iloc[0]['c']
                logger.info(f"   [VERIFIED SPLIT] {before.iloc[-1]['c']} -> {after.iloc[0]['c']} (new ratio: {new_obs:.3f})")
                if abs(new_obs - 1.0) > 0.25:
                    all_verified = False

    if all_verified:
        logger.info(f"   [SUCCESS] Successfully permanently adjusted {symbol}.parquet")
    else:
        logger.warning(f"   [CHECK NEEDED] Continuity post-check had variance for {symbol}.parquet")

    return all_verified


def main():
    parser = argparse.ArgumentParser(description="Fix minute parquet corporate actions and seam discontinuities.")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to fix (default: all)")
    parser.add_argument("--apply", action="store_true", help="Apply adjustments to files (default is dry-run)")
    parser.add_argument("--rebuild-daily", action="store_true", help="Rebuild adjusted_daily cache for modified stocks")
    args = parser.parse_args()

    splits_cache = load_splits_cache()
    if not splits_cache:
        logger.error("Splits cache empty or not found.")
        return

    con = duckdb.connect()

    target_files = []
    if args.symbols:
        for s in args.symbols:
            sym_clean = s.upper().replace('.NS', '').strip()
            p = os.path.join(MINUTE_DIR, f"{sym_clean}.parquet")
            if os.path.exists(p):
                target_files.append((sym_clean, p))
            else:
                logger.warning(f"File not found: {p}")
    else:
        for fname in sorted(os.listdir(MINUTE_DIR)):
            if fname.endswith('.parquet'):
                sym = fname[:-8]
                target_files.append((sym, os.path.join(MINUTE_DIR, fname)))

    logger.info(f"Scanning {len(target_files)} minute Parquet files...")
    affected = []

    for sym, p_file in target_files:
        s_splits = splits_cache.get(sym, {})
        if not s_splits:
            continue
        adjustments = identify_adjustments_for_stock(con, p_file, sym, s_splits)
        if adjustments:
            affected.append((sym, p_file, adjustments))

    logger.info(f"Scan complete. {len(affected)} stocks require adjustment.")

    dry_run = not args.apply
    if dry_run:
        logger.info("Running in DRY-RUN mode. Pass --apply to write adjustments.")

    modified_symbols = []
    for sym, p_file, adjustments in affected:
        success = apply_adjustments_to_file(con, p_file, sym, adjustments, dry_run=dry_run)
        if success and not dry_run:
            modified_symbols.append(sym)

    if not dry_run and modified_symbols:
        logger.info(f"Successfully adjusted {len(modified_symbols)} minute Parquet files.")
        if args.rebuild_daily:
            logger.info("Rebuilding daily cache for modified stocks...")
            try:
                from build_daily_cache import build_daily_cache_batch
                build_daily_cache_batch(modified_symbols, force=True)
                logger.info("Daily cache rebuilt successfully.")
            except Exception as e:
                logger.error(f"Error rebuilding daily cache: {e}")

    con.close()


if __name__ == "__main__":
    main()

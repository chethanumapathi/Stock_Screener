"""
Local Institutional Delivery Surge Screener (with 1Y Vol, Lifetime OBV, Monthly R1 & 200 EMA)
=============================================================================================
Queries the local consolidated Bhavcopy database (data/consolidated_data.csv)
using DuckDB for instant screening across any trading session.
"""

import os
import sys
import argparse
import datetime
import duckdb
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONSOLIDATED_FILE = os.path.join(BASE_DIR, 'data', 'consolidated_data.csv')

def run_local_screener(date_str=None, min_delivery_qty=25000, min_delivery_mult=5.0, min_price=20.0, min_turnover_lacs=50.0, top_n=30, strict_mode=True):
    if not os.path.exists(CONSOLIDATED_FILE):
        print(f"[!] Error: Consolidated file not found at {CONSOLIDATED_FILE}")
        return None

    con = duckdb.connect()

    # Determine date to screen
    if not date_str:
        latest_res = con.execute(f"SELECT MAX(Date) as max_date FROM '{CONSOLIDATED_FILE}'").fetchone()
        if not latest_res or not latest_res[0]:
            print("[!] Error: No dates found in database.")
            return None
        date_str = str(latest_res[0])

    print(f"[*] Screening local database for Institutional Delivery Surges on Date: {date_str}")
    print(f"    Filters: Delivery Spike >= {min_delivery_mult}x, 1Y Volume >= 8X & High, Lifetime High OBV, > Monthly R1, > Daily 200 EMA")

    # Extra filter condition if strict_mode is enabled
    strict_clause = """
      AND Volume >= max_vol_1y_prev
      AND (Volume / NULLIF(avg_vol_1y_prev, 0)) >= 8.0
      AND obv >= max_obv_lifetime
      AND Close > sma200
      AND (monthly_r1 IS NULL OR Close > monthly_r1)
    """ if strict_mode else ""

    sql = f"""
    WITH base AS (
        SELECT 
            Symbol,
            Date,
            Close,
            Prev_Close,
            Open,
            High,
            Low,
            Deliv_Qty,
            Deliv_Per,
            Volume,
            Turnover_Lacs,
            -- Month string for monthly pivot calculation
            SUBSTR(CAST(Date AS VARCHAR), 1, 7) as month_str,
            -- Delivery spike vs prior day & 20d avg
            LAG(Deliv_Qty, 1) OVER (PARTITION BY Symbol ORDER BY Date ASC) as prev_deliv_qty,
            AVG(Deliv_Qty) OVER (PARTITION BY Symbol ORDER BY Date ASC ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_deliv_20d,
            -- 1-Year volume highest & 1-year average (250 preceding sessions)
            MAX(Volume) OVER (PARTITION BY Symbol ORDER BY Date ASC ROWS BETWEEN 250 PRECEDING AND 1 PRECEDING) as max_vol_1y_prev,
            AVG(Volume) OVER (PARTITION BY Symbol ORDER BY Date ASC ROWS BETWEEN 250 PRECEDING AND 1 PRECEDING) as avg_vol_1y_prev,
            -- 200 EMA / SMA approximation
            AVG(Close) OVER (PARTITION BY Symbol ORDER BY Date ASC ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) as sma200,
            -- OBV step
            CASE 
                WHEN Close > Prev_Close THEN Volume
                WHEN Close < Prev_Close THEN -Volume
                ELSE 0
            END as obv_step
        FROM '{CONSOLIDATED_FILE}'
        WHERE Series = 'EQ'
          AND Symbol NOT LIKE '%ETF%'
          AND Symbol NOT LIKE '%BEES%'
          AND Symbol NOT LIKE '%GOLD%'
          AND Symbol NOT LIKE '%NIFTY%'
          AND Symbol NOT LIKE '%LIQUID%'
          AND Symbol NOT LIKE '%SENSEX%'
          AND Symbol NOT LIKE '%SILVER%'
          AND Volume > 0
    ),
    monthly_agg AS (
        SELECT 
            Symbol,
            month_str,
            MAX(High) as m_high,
            MIN(Low) as m_low,
            arg_max(Close, Date) as m_close
        FROM base
        GROUP BY Symbol, month_str
    ),
    monthly_pivots AS (
        SELECT 
            Symbol,
            month_str,
            -- Shift by 1 month for pivot convention
            LAG(m_high, 1) OVER (PARTITION BY Symbol ORDER BY month_str ASC) as prev_m_high,
            LAG(m_low, 1) OVER (PARTITION BY Symbol ORDER BY month_str ASC) as prev_m_low,
            LAG(m_close, 1) OVER (PARTITION BY Symbol ORDER BY month_str ASC) as prev_m_close
        FROM monthly_agg
    ),
    monthly_r1_calc AS (
        SELECT 
            Symbol,
            month_str,
            (2.0 * ((prev_m_high + prev_m_low + prev_m_close) / 3.0) - prev_m_low) as monthly_r1
        FROM monthly_pivots
    ),
    obv_calc AS (
        SELECT 
            b.*,
            mr.monthly_r1,
            SUM(b.obv_step) OVER (PARTITION BY b.Symbol ORDER BY b.Date ASC) as obv
        FROM base b
        LEFT JOIN monthly_r1_calc mr 
          ON b.Symbol = mr.Symbol AND b.month_str = mr.month_str
    ),
    obv_lifetime AS (
        SELECT 
            *,
            MAX(obv) OVER (PARTITION BY Symbol ORDER BY Date ASC) as max_obv_lifetime
        FROM obv_calc
    )
    SELECT 
        Symbol,
        Date,
        Close as CLOSE_PRICE,
        Prev_Close as PREV_CLOSE,
        ROUND(((Close - Prev_Close) / Prev_Close) * 100, 2) as PCT_CHANGE,
        Deliv_Qty as DelivQty,
        prev_deliv_qty as PrevDelivQty,
        ROUND(Deliv_Qty / NULLIF(prev_deliv_qty, 0), 2) as DelivMultiple,
        ROUND(Deliv_Qty / NULLIF(avg_deliv_20d, 0), 2) as DelivMult20D,
        Deliv_Per as DelivPct,
        Volume,
        ROUND(Volume / NULLIF(avg_vol_1y_prev, 0), 2) as Vol_Mult_1Y,
        (Volume >= max_vol_1y_prev) as Vol_1Y_High,
        (Volume / NULLIF(avg_vol_1y_prev, 0) >= 8.0) as Vol_8X_1Y,
        (obv >= max_obv_lifetime) as OBV_Life_High,
        ROUND(monthly_r1, 2) as Monthly_R1,
        (Close > monthly_r1) as Abv_Month_R1,
        ROUND(sma200, 2) as EMA200,
        (Close > sma200) as Abv_EMA200,
        Turnover_Lacs as TURNOVER_LACS
    FROM obv_lifetime
    WHERE Date = '{date_str}'
      AND Close > Prev_Close
      AND Close >= {min_price}
      AND Turnover_Lacs >= {min_turnover_lacs}
      AND Deliv_Qty >= {min_delivery_qty}
      AND (Deliv_Qty / NULLIF(prev_deliv_qty, 0)) >= {min_delivery_mult}
      {strict_clause}
    ORDER BY DelivMultiple DESC
    LIMIT {top_n}
    """

    df = con.execute(sql).fetchdf()

    output_csv = os.path.join(BASE_DIR, f"delivery_swing_candidates_{date_str.replace('-', '')}.csv")
    output_tv = os.path.join(BASE_DIR, f"tradingview_watchlist_{date_str.replace('-', '')}.txt")

    df.to_csv(output_csv, index=False)

    tv_tickers = [f"NSE:{s}" for s in df["Symbol"].tolist()]
    with open(output_tv, "w", encoding="utf-8") as f:
        f.write(", ".join(tv_tickers))

    mode_label = "STRICT (All Filters Applied: Deliv >= 5X, Vol >= 8X 1Y & High, Lifetime OBV, > Month R1, > 200 EMA)" if strict_mode else "ALL SPIKES (With Filter Flags)"
    print("\n" + "="*95)
    print(f" LOCAL SCREENING COMPLETE [{mode_label}]: Found {len(df)} Candidate(s) for {date_str}")
    print(f" Detailed CSV    : {output_csv}")
    print(f" TradingView List: {output_tv}")
    print("="*95)
    if not df.empty:
        cols_to_print = ['Symbol', 'CLOSE_PRICE', 'PCT_CHANGE', 'DelivMultiple', 'Vol_Mult_1Y', 'Vol_1Y_High', 'OBV_Life_High', 'Abv_Month_R1', 'Abv_EMA200']
        print(df[[c for c in cols_to_print if c in df.columns]].to_string(index=False))
    else:
        print(f"No stocks matched all criteria on {date_str}.")

    return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Institutional Delivery Surge Screener (with 1Y Vol, Lifetime OBV, Monthly R1 & 200 EMA)")
    parser.add_argument("--date", type=str, default=None, help="Date to screen (YYYY-MM-DD). Default: latest available date")
    parser.add_argument("--mult", type=float, default=5.0, help="Minimum delivery multiple vs prior day (default: 5.0)")
    parser.add_argument("--qty", type=int, default=25000, help="Minimum deliverable quantity (default: 25000)")
    parser.add_argument("--price", type=float, default=20.0, help="Minimum stock price (default: 20.0)")
    parser.add_argument("--turnover", type=float, default=50.0, help="Minimum turnover in lacs (default: 50.0)")
    parser.add_argument("--top", type=int, default=30, help="Max candidates to output (default: 30)")
    parser.add_argument("--all", action="store_true", help="Display all delivery spikes with filter flags rather than strict filtering")
    args = parser.parse_args()

    run_local_screener(
        date_str=args.date,
        min_delivery_qty=args.qty,
        min_delivery_mult=args.mult,
        min_price=args.price,
        min_turnover_lacs=args.turnover,
        top_n=args.top,
        strict_mode=not args.all
    )

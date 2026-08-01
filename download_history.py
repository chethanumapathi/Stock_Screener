import os
import sys
from datetime import datetime, timedelta
import time
import pandas as pd
import random
import io

# Import helper functions from existing app.py
try:
    from app import (
        clean_bhavcopy,
        download_bhavcopy_from_nse,
        format_date_for_url,
        update_consolidated_database,
        BHAV_DIR,
        CONSOLIDATED_FILE
    )
except ImportError as e:
    print(f"Error importing from app.py: {e}")
    sys.exit(1)

def main():
    print("=" * 60)
    print("NSE HISTORICAL DATA DOWNLOADER (2 YEARS)")
    print("=" * 60)

    # 1. Establish start and end dates (August 1, 2024 to August 1, 2026)
    start_date = datetime(2024, 8, 1)
    end_date = datetime(2026, 8, 1)
    
    print(f"Target date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # 2. Get list of dates already present in the consolidated file
    existing_dates = set()
    if os.path.exists(CONSOLIDATED_FILE) and os.path.getsize(CONSOLIDATED_FILE) > 0:
        try:
            print("Reading existing dates from consolidated database...")
            # Only load the Date column to keep it memory-efficient
            existing_df = pd.read_csv(CONSOLIDATED_FILE, usecols=['Date'])
            existing_dates = set(existing_df['Date'].dropna().unique())
            print(f"Found {len(existing_dates)} unique dates already in database.")
        except Exception as e:
            print(f"Warning: Could not read consolidated file dates ({e}). Rebuilding database from scratch.")

    # 3. Generate all weekdays in range
    current_date = start_date
    weekdays = []
    while current_date <= end_date:
        if current_date.weekday() < 5:  # 0 to 4 are Mon-Fri
            weekdays.append(current_date)
        current_date += timedelta(days=1)
    
    print(f"Total weekdays in range: {len(weekdays)}")

    # 4. Filter out dates already present in the database
    dates_to_process = []
    for d in weekdays:
        date_str = d.strftime('%Y-%m-%d')
        if date_str not in existing_dates:
            dates_to_process.append(d)
            
    print(f"Dates to process (excluding already downloaded): {len(dates_to_process)}")
    
    if not dates_to_process:
        print("No new dates to download. Database is already up to date!")
        return

    # 5. Process dates
    success_count = 0
    holiday_count = 0
    failed_count = 0
    batch_dfs = []
    
    os.makedirs(BHAV_DIR, exist_ok=True)
    
    try:
        for idx, d in enumerate(dates_to_process, 1):
            date_str = d.strftime('%Y-%m-%d')
            date_url_str = format_date_for_url(d)
            print(f"[{idx}/{len(dates_to_process)}] Processing {date_str}...")
            
            # Check local cache first
            filename = f"sec_bhavdata_full_{date_url_str}.csv"
            local_path = os.path.join(BHAV_DIR, filename)
            
            raw_csv_text = None
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                print(f"  -> Found in local cache: {local_path}")
                try:
                    with open(local_path, 'r', encoding='utf-8') as f:
                        raw_csv_text = f.read()
                except Exception as e:
                    print(f"  -> Error reading cached file: {e}")
            
            # If not in cache, download from NSE
            if not raw_csv_text:
                try:
                    raw_csv_text = download_bhavcopy_from_nse(d)
                    if raw_csv_text:
                        # Save to cache
                        with open(local_path, 'w', encoding='utf-8') as f:
                            f.write(raw_csv_text)
                        print(f"  -> Successfully downloaded and cached.")
                        success_count += 1
                        # Sleep to respect rate limits
                        sleep_time = random.uniform(0.5, 1.5)
                        time.sleep(sleep_time)
                    else:
                        print(f"  -> Data not available (likely weekend or holiday). Skipping.")
                        holiday_count += 1
                except Exception as e:
                    print(f"  -> Exception occurred: {e}")
                    failed_count += 1
                    time.sleep(2)  # Longer wait on error
                    continue
            else:
                success_count += 1
            
            # Parse and clean data if available
            if raw_csv_text:
                try:
                    df = pd.read_csv(io.StringIO(raw_csv_text))
                    cleaned = clean_bhavcopy(df)
                    if not cleaned.empty:
                        batch_dfs.append(cleaned)
                except Exception as e:
                    print(f"  -> Error parsing CSV: {e}")
                    failed_count += 1

            # Save batch to file periodically to prevent data loss
            if len(batch_dfs) >= 10:
                print("Writing batch to consolidated database...")
                combined_batch = pd.concat(batch_dfs, ignore_index=True)
                total_records = update_consolidated_database(combined_batch)
                batch_dfs = []
                print(f"Progress Saved. Current DB total: {total_records} records.")

    except KeyboardInterrupt:
        print("\nDownload interrupted by user. Saving current batch before exiting...")
        
    finally:
        # Save any remaining data in the final batch
        if batch_dfs:
            print("Writing final batch to consolidated database...")
            combined_batch = pd.concat(batch_dfs, ignore_index=True)
            total_records = update_consolidated_database(combined_batch)
            print(f"Current DB total: {total_records} records.")
            
        print("\n" + "=" * 60)
        print("HISTORICAL PROCESSING COMPLETE SUMMARY:")
        print(f"Successful downloads/loads: {success_count}")
        print(f"Holidays/Weekends skipped: {holiday_count}")
        print(f"Failed dates: {failed_count}")
        print("=" * 60)

if __name__ == "__main__":
    main()

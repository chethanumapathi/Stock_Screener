import json
import os
import re
from datetime import datetime

DEST_DIR = r"C:\Users\cheth\OneDrive\Desktop\Strategies"
JSON_PATH = r"c:\Stock_Screener\data\backtest_strategies.json"

os.makedirs(DEST_DIR, exist_ok=True)

with open(JSON_PATH, "r", encoding="utf-8") as f:
    strategies = json.load(f)

print(f"Loaded {len(strategies)} backtest strategies from {JSON_PATH}")

# 1. Master combined notepad file
master_filename = "ALL_BACKTEST_STRATEGIES_MASTER.txt"
master_path = os.path.join(DEST_DIR, master_filename)

master_content = []
master_content.append("=" * 90)
master_content.append("  CHETHANQUANT STOCK SCREENER & BACKTESTER - MASTER STRATEGIES REPOSITORY")
master_content.append(f"  Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
master_content.append(f"  Total Strategies: {len(strategies)}")
master_content.append(f"  Storage Directory: {DEST_DIR}")
master_content.append("=" * 90)
master_content.append("\nTABLE OF CONTENTS:")
master_content.append("-" * 90)

for idx, s in enumerate(strategies, 1):
    master_content.append(f"  [{idx:02d}] {s.get('name', 'Untitled')}")

master_content.append("-" * 90)
master_content.append("\n" * 2)

for idx, s in enumerate(strategies, 1):
    name = s.get('name', f'Strategy {idx}')
    code = s.get('code', '')
    
    # Add to master
    master_content.append("=" * 90)
    master_content.append(f"STRATEGY {idx:02d}: {name}")
    master_content.append("=" * 90)
    master_content.append(code.strip())
    master_content.append("\n" * 3)
    
    # 2. Individual notepad file for each strategy
    clean_name = re.sub(r'[\\/*?:"<>|]', '-', name).strip()
    clean_name = re.sub(r'\s+', ' ', clean_name)
    individual_filename = f"{idx:02d} - {clean_name}.txt"
    individual_path = os.path.join(DEST_DIR, individual_filename)
    
    individual_content = [
        "=" * 80,
        f"Strategy {idx:02d}: {name}",
        f"ChethanQuant Backtest Strategy Repository",
        f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 80,
        "",
        code.strip(),
        ""
    ]
    
    with open(individual_path, "w", encoding="utf-8") as ind_f:
        ind_f.write("\n".join(individual_content))
    
    print(f"Saved: {individual_filename} ({len(code)} characters)")

# Write master file
with open(master_path, "w", encoding="utf-8") as m_f:
    m_f.write("\n".join(master_content))

print(f"\nSuccessfully wrote master notepad file: {master_path}")
print(f"Total {len(strategies)} individual notepad files saved to: {DEST_DIR}")

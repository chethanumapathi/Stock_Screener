import os
import json
import re
from datetime import datetime

# 1. Read the newly created strategy
with open('strategies/quarterly_profit_growth_weekly_ema_stack.py', 'r', encoding='utf-8') as f:
    new_strategy_code = f.read()

new_strategy_name = 'Quarterly YoY Profit > 100% + Weekly 10/30/40 EMA Stack Strategy'

# 2. Rebuild the complete list of 29 strategies
desktop_dir = r'C:\Users\cheth\OneDrive\Desktop\Strategies'

all_strategies = []
txt_files = sorted([f for f in os.listdir(desktop_dir) if f.endswith('.txt') and re.match(r'^\d{2}\s*-\s*', f)])
print(f"Found {len(txt_files)} existing strategy files in Desktop/Strategies")

for f in txt_files:
    path = os.path.join(desktop_dir, f)
    with open(path, 'r', encoding='utf-8') as fp:
        content = fp.read()
    
    # Extract name and code
    lines = content.split('\n')
    strat_name = f[5:].replace('.txt', '').strip()
    for l in lines[:10]:
        if l.startswith('Strategy ') and ':' in l:
            strat_name = l.split(':', 1)[1].strip()
            break
            
    code_start_idx = 0
    divider_count = 0
    for idx, l in enumerate(lines):
        if l.startswith('=' * 20):
            divider_count += 1
            if divider_count == 2:
                code_start_idx = idx + 1
                break
    code_body = '\n'.join(lines[code_start_idx:]).strip()
    all_strategies.append({'name': strat_name, 'code': code_body})

# Append 29th strategy
all_strategies.append({'name': new_strategy_name, 'code': new_strategy_code.strip()})
print(f"Total strategies now: {len(all_strategies)}")

# 3. Save to data/backtest_strategies.json
with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(all_strategies, f, indent=4)
print("Updated data/backtest_strategies.json with all 29 strategies")

# 4. Save individual file 29
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
ind_file_29 = os.path.join(desktop_dir, '29 - Quarterly YoY Profit - 100% + Weekly 10-30-40 EMA Stack Strategy.txt')
ind_content = [
    '=' * 80,
    f'Strategy 29: {new_strategy_name}',
    'ChethanQuant Backtest Strategy Repository',
    f'Exported: {now_str}',
    '=' * 80,
    '',
    new_strategy_code.strip(),
    ''
]
with open(ind_file_29, 'w', encoding='utf-8') as fp:
    fp.write('\n'.join(ind_content))
print(f"Saved individual Notepad file: {ind_file_29}")

# 5. Re-generate ALL_BACKTEST_STRATEGIES_MASTER.txt with all 29 strategies
master_file = os.path.join(desktop_dir, 'ALL_BACKTEST_STRATEGIES_MASTER.txt')
master_lines = []
master_lines.append('=' * 90)
master_lines.append('  CHETHANQUANT STOCK SCREENER & BACKTESTER - MASTER STRATEGIES REPOSITORY')
master_lines.append(f'  Generated on: {now_str}')
master_lines.append(f'  Total Strategies: {len(all_strategies)}')
master_lines.append(f'  Storage Directory: {desktop_dir}')
master_lines.append('=' * 90)
master_lines.append('\nTABLE OF CONTENTS:')
master_lines.append('-' * 90)
for idx, s in enumerate(all_strategies, 1):
    master_lines.append(f"  [{idx:02d}] {s.get('name')}")
master_lines.append('-' * 90)
master_lines.append('\n' * 2)

for idx, s in enumerate(all_strategies, 1):
    master_lines.append('=' * 90)
    master_lines.append(f"STRATEGY {idx:02d}: {s.get('name')}")
    master_lines.append('=' * 90)
    master_lines.append(s.get('code', '').strip())
    master_lines.append('\n' * 3)

with open(master_file, 'w', encoding='utf-8') as fp:
    fp.write('\n'.join(master_lines))
print(f"Updated Master Notepad file: {master_file} ({len(all_strategies)} strategies)")

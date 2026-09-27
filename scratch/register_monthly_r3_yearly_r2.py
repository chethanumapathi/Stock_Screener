import os
import json
import re
from datetime import datetime

STRATEGY_NAME = "Daily Monthly-R3 Breakout above Yearly-R2 (TP 40% | SL Daily Close Below Yearly R2)"
STRATEGY_FILE = "strategies/daily_monthly_r3_yearly_r2_breakout.py"

with open(STRATEGY_FILE, 'r', encoding='utf-8') as f:
    strategy_code = f.read()

# 1. Update data/backtest_strategies.json
backtest_json = "data/backtest_strategies.json"
if os.path.exists(backtest_json):
    with open(backtest_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    found = False
    for s in data:
        if s.get('name') == STRATEGY_NAME:
            s['code'] = strategy_code
            found = True
            break
    if not found:
        data.append({'name': STRATEGY_NAME, 'code': strategy_code})
    with open(backtest_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f"Updated {backtest_json} (total: {len(data)})")

# 2. Update data/strategies.json
screener_json = "data/strategies.json"
if os.path.exists(screener_json):
    with open(screener_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    found = False
    for s in data:
        if s.get('name') == STRATEGY_NAME:
            s['code'] = strategy_code
            found = True
            break
    if not found:
        data.append({'name': STRATEGY_NAME, 'code': strategy_code})
    with open(screener_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f"Updated {screener_json} (total: {len(data)})")

# 3. Export to Desktop Strategies folder if present
desktop_dir = r"C:\Users\cheth\OneDrive\Desktop\Strategies"
if os.path.exists(desktop_dir):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ind_file = os.path.join(desktop_dir, "30 - Daily Monthly-R3 Breakout above Yearly-R2 Strategy.txt")
    ind_content = [
        "=" * 80,
        f"Strategy 30: {STRATEGY_NAME}",
        "ChethanQuant Backtest Strategy Repository",
        f"Exported: {now_str}",
        "=" * 80,
        "",
        strategy_code.strip(),
        ""
    ]
    with open(ind_file, 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(ind_content))
    print(f"Saved: {ind_file}")

    # Re-generate Master
    txt_files = sorted([f for f in os.listdir(desktop_dir) if f.endswith('.txt') and re.match(r'^\d{2}\s*-\s*', f)])
    print(f"Total numbered strategy files found on Desktop: {len(txt_files)}")
    all_strategies = []
    for f in txt_files:
        path = os.path.join(desktop_dir, f)
        with open(path, 'r', encoding='utf-8') as fp:
            content = fp.read()
        lines = content.split('\n')
        s_name = f[5:].replace('.txt', '').strip()
        for l in lines[:10]:
            if l.startswith('Strategy ') and ':' in l:
                s_name = l.split(':', 1)[1].strip()
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
        all_strategies.append({'name': s_name, 'code': code_body})

    master_file = os.path.join(desktop_dir, "ALL_BACKTEST_STRATEGIES_MASTER.txt")
    master_lines = [
        "=" * 90,
        "  CHETHANQUANT STOCK SCREENER & BACKTESTER - MASTER STRATEGIES REPOSITORY",
        f"  Generated on: {now_str}",
        f"  Total Strategies: {len(all_strategies)}",
        f"  Storage Directory: {desktop_dir}",
        "=" * 90,
        "\nTABLE OF CONTENTS:",
        "-" * 90
    ]
    for idx, s in enumerate(all_strategies, 1):
        master_lines.append(f"  [{idx:02d}] {s.get('name')}")
    master_lines.append("-" * 90)
    master_lines.append("\n\n")

    for idx, s in enumerate(all_strategies, 1):
        master_lines.append("=" * 90)
        master_lines.append(f"STRATEGY {idx:02d}: {s.get('name')}")
        master_lines.append("=" * 90)
        master_lines.append(s.get('code', '').strip())
        master_lines.append("\n\n\n")

    with open(master_file, 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(master_lines))
    print(f"Updated Master file: {master_file} ({len(all_strategies)} strategies)")

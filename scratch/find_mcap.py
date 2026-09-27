import re
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

print("=== Checking templates/index.html ===")
with open('templates/index.html', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# Find the min-mcap-select block
match = re.search(r'(<select[^>]*id=["\']min-mcap-select["\'].*?</select>)', text, re.DOTALL)
if match:
    print(match.group(1))

match_bt = re.search(r'(<select[^>]*id=["\']bt-min-mcap-select["\'].*?</select>)', text, re.DOTALL)
if match_bt:
    print(match_bt.group(1))

print("\n=== Checking static/js/app.js ===")
with open('static/js/app.js', 'r', encoding='utf-8', errors='ignore') as f:
    js_text = f.read()

for i, line in enumerate(js_text.splitlines(), 1):
    if 'min-mcap-select' in line or 'minMarketCap' in line or 'min_market_cap' in line:
        print(f"  js:{i}: {line.strip()}")

print("\n=== Checking app.py ===")
with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
    app_text = f.read()

for i, line in enumerate(app_text.splitlines(), 1):
    if any(k in line for k in ['min-mcap', 'min_market_cap', 'minMarketCap', 'market_cap_cr']):
        print(f"  app.py:{i}: {line.strip()}")

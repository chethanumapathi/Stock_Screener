import os
import json
import duckdb
import pandas as pd
import numpy as np

# Load strategy code from scratch/strong_buy_scan_current.py
with open('scratch/strong_buy_scan_current.py', 'r', encoding='utf-8') as f:
    orig_code = f.read()

# Build amended version
amended_code = orig_code

# Let's inspect how _compute_pivot_r2 and simulate_trades are structured in strong_buy_scan_current.py
print("Loaded original code length:", len(orig_code))

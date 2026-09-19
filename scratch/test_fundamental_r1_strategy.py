import os
import json
import pandas as pd
import numpy as np

# Load statement data helper
def _load_statement_data(symbol: str) -> dict:
    if not symbol:
        return {}
    try:
        if 'get_stock_statement' in globals() and callable(globals()['get_stock_statement']):
            res = globals()['get_stock_statement'](symbol, fetch_online=False)
            if res:
                return res
        try:
            from app import get_stock_statement
            res = get_stock_statement(symbol, fetch_online=False)
            if res:
                return res
        except Exception:
            pass
        import os, json
        clean_sym = str(symbol).upper().replace('.NS', '').strip()
        stmt_path = os.path.join('data', 'fundamentals', 'statements', f"{clean_sym}.json")
        if os.path.exists(stmt_path):
            with open(stmt_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def check_qoq_profit_increasing(symbol: str, quarters: int = 2) -> bool:
    if not symbol or quarters <= 0:
        return False
    stmt = _load_statement_data(symbol)
    if not stmt:
        return False
    qpnl = stmt.get('quarterly_pnl', {})
    metrics = qpnl.get('metrics', {})
    ni_dict = (
        metrics.get('Net Income') or
        metrics.get('Net Income Common Stockholders') or
        metrics.get('Normalized Income') or
        metrics.get('Net Income Including Noncontrolling Interests') or
        metrics.get('Net Profit')
    )
    if not ni_dict:
        return False

    dates = qpnl.get('dates', [])
    needed = quarters + 1
    ni_vals = []
    for d in dates:
        v = ni_dict.get(d)
        if v is not None and not pd.isna(v):
            try:
                val = float(v)
                ni_vals.append(val)
                if len(ni_vals) == needed:
                    break
            except (ValueError, TypeError):
                pass

    if len(ni_vals) < needed:
        return False

    # 1. Must be strictly profitable (> 0) in all checked quarters
    for v in ni_vals:
        if v <= 0:
            return False

    # 2. Must be strictly increasing QoQ: Q0 > Q1 > Q2
    for i in range(quarters):
        if ni_vals[i] <= ni_vals[i + 1]:
            return False

    return True

print("ICICIBANK passes:", check_qoq_profit_increasing("ICICIBANK", 2))
print("TRENT passes:", check_qoq_profit_increasing("TRENT", 2))
print("BHARTIARTL passes:", check_qoq_profit_increasing("BHARTIARTL", 2))

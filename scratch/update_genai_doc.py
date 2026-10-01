with open('docs/GENAI_STRATEGY_TEMPLATE.md', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update section 6
t1 = '     - Returns: `exit_idx, exit_price, exit_reason, mae_pct, mfe_pct`.\n   - Implement `simulate_trades(df)` returning a pandas DataFrame of trades.'
r1 = '     - Returns: `exit_idx, exit_price, exit_reason, mae_pct, mfe_pct`.\n     - If trade reaches end of data without exiting: return `n - 1, close[-1], "Still Running", mae_pct, mfe_pct`.\n   - Still Running Trades Invariant:\n     * Unclosed trades at the end of data must have `exit_date = "-"`, `exit_reason = "Still Running"`, and `is_open = True`.\n     * Completed exits (TP, SL, Timeout) must have `is_open = False`.\n   - Implement `simulate_trades(df)` returning a pandas DataFrame of trades.'

# 2. Update _simulate_one_trade return
t2 = 'return n - 1, close[-1], "End of Data", mae_pct, mfe_pct'
r2 = 'return n - 1, close[-1], "Still Running", mae_pct, mfe_pct'

# 3. Update trades.append block
t3 = '''        trades.append({
            "entry_date": str(date_strs[idx])[:10],
            "entry_price": round(float(ep), 2),
            "exit_date": str(date_strs[ex_idx])[:10],
            "exit_price": round(float(ex_p), 2),
            "exit_reason": reason,
            "mae_pct": round(float(mae_pct), 2),
            "mfe_pct": round(float(mfe_pct), 2),
            "is_open": (reason == "End of Data")
        })'''

r3 = '''        is_running = (reason == "Still Running" or reason == "End of Data")
        trades.append({
            "entry_date": str(date_strs[idx])[:10],
            "entry_price": round(float(ep), 2),
            "exit_date": "-" if is_running else str(date_strs[ex_idx])[:10],
            "exit_price": round(float(ex_p), 2),
            "exit_reason": "Still Running" if is_running else reason,
            "mae_pct": round(float(mae_pct), 2),
            "mfe_pct": round(float(mfe_pct), 2),
            "is_open": is_running
        })'''

def apply_repl(text, target, repl):
    if target in text:
        return text.replace(target, repl)
    target_crlf = target.replace('\n', '\r\n')
    repl_crlf = repl.replace('\n', '\r\n')
    if target_crlf in text:
        return text.replace(target_crlf, repl_crlf)
    print(f"Warning: target not found: {target[:40]}...")
    return text

content = apply_repl(content, t1, r1)
content = apply_repl(content, t2, r2)
content = apply_repl(content, t3, r3)

with open('docs/GENAI_STRATEGY_TEMPLATE.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated docs/GENAI_STRATEGY_TEMPLATE.md successfully!")

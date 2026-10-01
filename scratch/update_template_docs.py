with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

target = '     - Returns: `exit_idx, exit_price, exit_reason, mae_pct, mfe_pct`.\n   - Implement `simulate_trades(df)` returning a pandas DataFrame of trades.'
replacement = '     - Returns: `exit_idx, exit_price, exit_reason, mae_pct, mfe_pct`.\n     - If trade reaches end of data without exiting: return `n - 1, close[-1], "Still Running", mae_pct, mfe_pct`.\n   - Still Running Trades Invariant:\n     * Unclosed trades at the end of data must have `exit_date = "-"`, `exit_reason = "Still Running"`, and `is_open = True`.\n     * Completed exits (TP, SL, Timeout) must have `is_open = False`.\n   - Implement `simulate_trades(df)` returning a pandas DataFrame of trades.'

target_crlf = target.replace('\n', '\r\n')
replacement_crlf = replacement.replace('\n', '\r\n')

if target in content:
    content = content.replace(target, replacement)
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Updated templates/index.html with LF')
elif target_crlf in content:
    content = content.replace(target_crlf, replacement_crlf)
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Updated templates/index.html with CRLF')
else:
    print('Target string not found in templates/index.html')

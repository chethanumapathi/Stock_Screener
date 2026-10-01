import json
import os
import re

print("=== 1. Updating data/backtest_strategies.json ===")
with open('data/backtest_strategies.json', 'r', encoding='utf-8') as f:
    bt_strats = json.load(f)

for s in bt_strats:
    name = s.get('name', '')
    code = s.get('code', '')

    if 'Strong Buy Scan' in name:
        print(f"Updating: {name}")
        # Update close_trade definition
        code = code.replace(
            "'exit_date': date_strs[i],",
            "'exit_date': '-' if is_open else date_strs[i],"
        )
        code = code.replace(
            "'exit_reason': reason,",
            "'exit_reason': 'Still Running' if is_open else reason,"
        )
        code = code.replace(
            "close_trade(i, close[i], 'Open', is_open=True)",
            "close_trade(i, close[i], 'Still Running', is_open=True)"
        )
        s['code'] = code

    elif '5-Min Daily R3' in name:
        print(f"Updating: {name}")
        code = re.sub(
            r'"exit_date":\s*dates\[-1\],\s*"exit_price":\s*round\(float\(close\[-1\]\),\s*2\),\s*"exit_reason":\s*"End of Data",',
            r'"exit_date": "-",\n            "exit_price": round(float(close[-1]), 2),\n            "exit_reason": "Still Running",',
            code
        )
        s['code'] = code

    elif 'Best Swing Trade' in name:
        print(f"Updating: {name}")
        # Fix OPEN_TIMEOUT
        code = code.replace(
            '"exit_reason": "OPEN_TIMEOUT",\n                    "mae_pct": round(float(mae), 2),\n                    "mfe_pct": round(float(mfe), 2),\n                    "is_open": True,',
            '"exit_reason": "Max Hold Bars Timeout",\n                    "mae_pct": round(float(mae), 2),\n                    "mfe_pct": round(float(mfe), 2),\n                    "is_open": False,'
        )
        # Fix Target Profit string
        code = code.replace(
            '"exit_reason": "Target Profit (100%)",',
            '"exit_reason": f"Target Profit ({int(TP_PCT)}%)",'
        )
        code = code.replace(
            '"exit_reason": "Target Profit (100% Same Bar)",',
            '"exit_reason": f"Target Profit ({int(TP_PCT)}% Same Bar)",'
        )
        # Fix End of Data
        code = code.replace(
            '"exit_date": dates[-1],\n            "exit_price": round(float(close[-1]), 2),\n            "exit_reason": "End of Data",\n            "mae_pct": round(float(mae), 2),\n            "mfe_pct": round(float(mfe), 2),\n            "is_open": True,',
            '"exit_date": "-",\n            "exit_price": round(float(close[-1]), 2),\n            "exit_reason": "Still Running",\n            "mae_pct": round(float(mae), 2),\n            "mfe_pct": round(float(mfe), 2),\n            "is_open": True,'
        )
        code = code.replace(
            '"exit_date": dates[-1],\n            "exit_price": round(float(close[-1]), 2),\n            "exit_reason": "End of Data",\n            "mae_pct": round(float(mae), 2),\n            "mfe_pct": round(float(mfe), 2),\n            "is_open": False,',
            '"exit_date": "-",\n            "exit_price": round(float(close[-1]), 2),\n            "exit_reason": "Still Running",\n            "mae_pct": round(float(mae), 2),\n            "mfe_pct": round(float(mfe), 2),\n            "is_open": True,'
        )
        s['code'] = code

    elif '15-Min Volume Breakout' in name:
        print(f"Updating: {name}")
        code = code.replace(
            '"exit_date": date_strs[exit_idx],',
            '"exit_date": "-" if is_open else date_strs[exit_idx],'
        )
        code = code.replace(
            '"exit_reason": reason,',
            '"exit_reason": "Still Running" if is_open else reason,'
        )
        code = code.replace(
            'close_trade(n_bars - 1, close_5m[-1], "Open", is_open=True)',
            'close_trade(n_bars - 1, close_5m[-1], "Still Running", is_open=True)'
        )
        s['code'] = code

with open('data/backtest_strategies.json', 'w', encoding='utf-8') as f:
    json.dump(bt_strats, f, indent=4)
print("Saved data/backtest_strategies.json")


print("\n=== 2. Updating data/strategies.json ===")
with open('data/strategies.json', 'r', encoding='utf-8') as f:
    screen_strats = json.load(f)

for s in screen_strats:
    name = s.get('name', '')
    code = s.get('code', '')

    if '15-Min Intraday Dual RSI' in name or '1-Hour Weekly R3' in name or 'Weekly R3 Trigger' in name:
        print(f"Updating: {name}")
        code = code.replace(
            '"exit_date": date_strs[exit_idx],',
            '"exit_date": "-" if is_open else date_strs[exit_idx],'
        )
        code = code.replace(
            '"exit_reason": reason,',
            '"exit_reason": "Still Running" if is_open else reason,'
        )
        code = code.replace(
            'close_trade(n - 1, close[-1], "End of Data", is_open=True)',
            'close_trade(n - 1, close[-1], "Still Running", is_open=True)'
        )
        s['code'] = code

    elif '5-Min Daily R3' in name:
        print(f"Updating: {name}")
        code = re.sub(
            r'"exit_date":\s*dates\[-1\],\s*"exit_price":\s*round\(float\(close\[-1\]\),\s*2\),\s*"exit_reason":\s*"End of Data",',
            r'"exit_date": "-",\n            "exit_price": round(float(close[-1]), 2),\n            "exit_reason": "Still Running",',
            code
        )
        s['code'] = code

    elif '15-Min Volume Breakout' in name:
        print(f"Updating: {name}")
        code = code.replace(
            '"exit_date": date_strs[exit_idx],',
            '"exit_date": "-" if is_open else date_strs[exit_idx],'
        )
        code = code.replace(
            '"exit_reason": reason,',
            '"exit_reason": "Still Running" if is_open else reason,'
        )
        code = code.replace(
            'close_trade(n_bars - 1, close_5m[-1], "Open", is_open=True)',
            'close_trade(n_bars - 1, close_5m[-1], "Still Running", is_open=True)'
        )
        s['code'] = code

with open('data/strategies.json', 'w', encoding='utf-8') as f:
    json.dump(screen_strats, f, indent=4)
print("Saved data/strategies.json")

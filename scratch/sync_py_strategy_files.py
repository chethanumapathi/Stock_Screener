import os
import re

files_to_update = [
    'strategies/five_min_daily_r3_rsi85_ema50_sl.py',
    'strategies/fifteen_min_volume_300_daily_r3_rsi88.py',
    'strategies/fifteen_min_weekly_r3_r2_rsi80.py',
    'strategies/hourly_weekly_r3_supertrend.py',
    'strategies/intraday_rsi_volume_vwap_r2.py',
    'strategies/quarterly_profit_growth_weekly_ema_stack.py',
    'strategies/weekly_yearly_r1_daily_monthly_r1.py',
    'strategies/daily_rsi85_weekly_ema_stack.py',
]

for fpath in files_to_update:
    if not os.path.exists(fpath):
        continue
    with open(fpath, 'r', encoding='utf-8') as f:
        code = f.read()

    orig = code

    # 1. Update close_trade definition if present
    code = code.replace(
        '"exit_date": date_strs[exit_idx],',
        '"exit_date": "-" if is_open else date_strs[exit_idx],'
    )
    code = code.replace(
        "'exit_date': date_strs[exit_idx],",
        "'exit_date': '-' if is_open else date_strs[exit_idx],"
    )
    code = code.replace(
        '"exit_reason": reason,',
        '"exit_reason": "Still Running" if is_open else reason,'
    )
    code = code.replace(
        "'exit_reason': reason,",
        "'exit_reason': 'Still Running' if is_open else reason,"
    )
    code = code.replace(
        'close_trade(n - 1, close[-1], "End of Data", is_open=True)',
        'close_trade(n - 1, close[-1], "Still Running", is_open=True)'
    )
    code = code.replace(
        'close_trade(n_bars - 1, close_5m[-1], "Open", is_open=True)',
        'close_trade(n_bars - 1, close_5m[-1], "Still Running", is_open=True)'
    )

    # 2. Update direct End of Data appends
    code = re.sub(
        r'"exit_date":\s*dates_1m\[-1\],\s*"exit_price":\s*round\(float\(close_1m\[-1\]\),\s*2\),\s*"exit_reason":\s*"End of Data",',
        r'"exit_date": "-",\n            "exit_price": round(float(close_1m[-1]), 2),\n            "exit_reason": "Still Running",',
        code
    )
    code = re.sub(
        r'"exit_date":\s*dates\[-1\],\s*"exit_price":\s*round\(float\(close\[-1\]\),\s*2\),\s*"exit_reason":\s*"End of Data",',
        r'"exit_date": "-",\n            "exit_price": round(float(close[-1]), 2),\n            "exit_reason": "Still Running",',
        code
    )

    # 3. Timeout exits: ensure is_open: False
    code = code.replace(
        '"exit_reason": "OPEN_TIMEOUT",\n                    "mae_pct": round(float(mae), 2),\n                    "mfe_pct": round(float(mfe), 2),\n                    "is_open": True,',
        '"exit_reason": "Max Hold Bars Timeout",\n                    "mae_pct": round(float(mae), 2),\n                    "mfe_pct": round(float(mfe), 2),\n                    "is_open": False,'
    )
    code = code.replace(
        '"exit_reason": "OPEN_TIMEOUT",\n                    "is_open": True,',
        '"exit_reason": "Max Hold Bars Timeout",\n                    "is_open": False,'
    )

    # 4. In weekly_yearly_r1_daily_monthly_r1.py
    code = code.replace(
        'return n - 1, close[-1], "End of Data", mae_pct, mfe_pct',
        'return n - 1, close[-1], "Still Running", mae_pct, mfe_pct'
    )
    code = code.replace(
        '"is_open": (reason == "End of Data")',
        '"is_open": (reason in ["Still Running", "End of Data"])'
    )
    code = code.replace(
        '"exit_date": str(date_strs[ex_idx])[:10],',
        '"exit_date": "-" if (reason in ["Still Running", "End of Data"]) else str(date_strs[ex_idx])[:10],'
    )

    # 5. In quarterly_profit_growth_weekly_ema_stack.py
    code = code.replace(
        "'exit_reason': 'End of Data (Running)',",
        "'exit_reason': 'Still Running',"
    )
    code = code.replace(
        "'exit_date': dates[-1],",
        "'exit_date': '-',"
    )

    if code != orig:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(code)
        print(f"Updated {fpath}")
    else:
        print(f"No changes needed for {fpath}")

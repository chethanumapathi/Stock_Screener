"""
Quarterly YoY Profit Growth (>100%) + Weekly 10/30/40 EMA Stack Strategy
========================================================================

RULES:
1. FUNDAMENTAL CRITERIA:
   - Quarterly YoY Profit Growth grew by more than 100% (profit doubled
     compared to the same quarter of previous year, or grew >100% from previous quarter).
   - Reads directly from verified quarterly financial statements in data/fundamentals/statements/.
   - Point-in-time compliant: checks statements available prior to or on the trading date.

2. TECHNICAL SETUP (Weekly Timeframe):
   - Weekly candles must be in strictly stacked bullish order:
       Weekly Close > 10 EMA > 30 EMA > 40 EMA
   - When a weekly candle qualifies with this criteria, its HIGH is armed for breakout.
   - If any subsequent candle qualifies, its high can also update the armed level.
   - BUY ENTRY: We BUY at the HIGH of this qualifying candle when the next candle breaks this high.

3. EXIT (Trailing Stop Loss & Target):
   - Trailing rule: Watches for any weekly candle that closes BELOW the 30 EMA (Close < 30 EMA).
   - When a candle closes below 30 EMA, that candle's LOW is armed as the exit threshold.
   - If the NEXT candle breaks this low (Low < Armed Low), we EXIT the trade immediately.
   - If price closes back above 30 EMA before the low is broken, the breakdown is cancelled/disarmed.

DUAL TIMEFRAME COMPATIBILITY:
- Runs natively on Weekly candles (timeframe='1w').
- Also supports Daily candles (timeframe='1d') by dynamically resampling to weekly bars.
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

# ==============================================================================
# STRATEGY CONFIGURATION PARAMETERS
# ==============================================================================
MIN_PROFIT_GROWTH_PCT = 100.0     # Quarterly profit growth must be > 100% (doubled)
REQUIRE_FUNDAMENTALS = True       # True: require YoY/QoQ profit >100%; False: pure technicals
POINT_IN_TIME_FUNDAMENTALS = True # Only check quarterly statements reported up to trading date
EMA_FAST = 10                     # Fast Weekly EMA
EMA_MID = 30                      # Mid Weekly EMA
EMA_SLOW = 40                     # Slow Weekly EMA
MAX_ARMED_BARS = 3                # Keep armed breakout level active for up to N subsequent bars


def _get_quarterly_profit_history(symbol: str):
    """Loads quarterly financial statement profit metrics for the symbol."""
    try:
        clean_sym = str(symbol).upper().replace('.NS', '').replace('.BO', '').strip()
        stmt_path = os.path.join('data', 'fundamentals', 'statements', f'{clean_sym}.json')
        if not os.path.exists(stmt_path):
            return None
        with open(stmt_path, 'r', encoding='utf-8') as f:
            stmt = json.load(f)
        metrics = stmt.get('quarterly_pnl', {}).get('metrics', {})
        pdict = (
            metrics.get('Net Income') or
            metrics.get('Net Income Common Stockholders') or
            metrics.get('Net Profit') or
            metrics.get('Profit After Tax') or
            metrics.get('Pretax Income') or
            metrics.get('Operating Income')
        )
        if not pdict:
            return None
        sorted_q = sorted([(dt, float(pdict[dt])) for dt in pdict if pdict[dt] is not None], key=lambda x: x[0])
        return sorted_q
    except Exception:
        return None


def is_profit_doubled_as_of(quarters_list, as_of_date_str: str) -> bool:
    """
    Checks if quarterly profit grew by >100% either:
    1. YoY: current quarter vs same quarter 1 year ago (4 quarters prior)
    2. QoQ: current quarter vs immediately preceding quarter (1 quarter prior)
    """
    if not quarters_list:
        return False
    
    filtered = [q for q in quarters_list if q[0] <= as_of_date_str] if POINT_IN_TIME_FUNDAMENTALS else quarters_list
    if len(filtered) < 2:
        return False
        
    idx = len(filtered) - 1
    curr_dt, curr_val = filtered[idx]
    
    # 1. Check YoY (vs 4 quarters prior)
    if idx >= 4:
        prior_y_dt, prior_y_val = filtered[idx - 4]
        if prior_y_val > 0:
            yoy_growth = ((curr_val - prior_y_val) / prior_y_val) * 100.0
            if yoy_growth >= MIN_PROFIT_GROWTH_PCT:
                return True
                
    # 2. Check QoQ (vs 1 quarter prior)
    if idx >= 1:
        prior_q_dt, prior_q_val = filtered[idx - 1]
        if prior_q_val > 0:
            qoq_growth = ((curr_val - prior_q_val) / prior_q_val) * 100.0
            if qoq_growth >= MIN_PROFIT_GROWTH_PCT:
                return True
                
    return False


def screen(df: pd.DataFrame) -> dict:
    """Screener function compatible with Screener Engine."""
    return backtest(df)


def backtest(df: pd.DataFrame) -> dict:
    """
    Backtest function compatible with Backtest Engine.
    Simulates full lifecycle trades with trailing 30 EMA exit.
    """
    if df is None or len(df) < 30:
        return {
            'long_entry': pd.Series(False, index=df.index if df is not None else []),
            'tp_pct': 1.0,
            'sl_pct': 0.15,
            'trades': []
        }
        
    symbol = str(df.get('Symbol', df.get('symbol', ['UNKNOWN'])).iloc[0] if 'Symbol' in df.columns or 'symbol' in df.columns else 'UNKNOWN')
    quarters = _get_quarterly_profit_history(symbol) if REQUIRE_FUNDAMENTALS else None
    
    c_open = df['open'] if 'open' in df.columns else df['Open']
    c_high = df['high'] if 'high' in df.columns else df['High']
    c_low = df['low'] if 'low' in df.columns else df['Low']
    c_close = df['close'] if 'close' in df.columns else df['Close']
    
    # Dual-timeframe detection: if daily, resample to weekly; if weekly, use directly
    is_daily = len(df) > 300 and (pd.to_datetime(df.index[-1]) - pd.to_datetime(df.index[0])).days / len(df) < 3.0
    if is_daily:
        temp_df = pd.DataFrame({'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close})
        temp_df.index = pd.to_datetime(temp_df.index)
        w_df = temp_df.resample('W-FRI').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    else:
        w_df = pd.DataFrame({'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close})
        w_df.index = pd.to_datetime(w_df.index)
        
    # Calculate Weekly EMAs: 10, 30, 40
    w_df['ema10'] = w_df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    w_df['ema30'] = w_df['close'].ewm(span=EMA_MID, adjust=False).mean()
    w_df['ema40'] = w_df['close'].ewm(span=EMA_SLOW, adjust=False).mean()
    
    # Strictly in order: Candle Close > 10 EMA > 30 EMA > 40 EMA
    w_df['qualifies'] = (w_df['close'] > w_df['ema10']) & (w_df['ema10'] > w_df['ema30']) & (w_df['ema30'] > w_df['ema40'])
    
    dates = [str(d)[:10] for d in w_df.index]
    opens = w_df['open'].to_numpy(dtype=float)
    highs = w_df['high'].to_numpy(dtype=float)
    lows = w_df['low'].to_numpy(dtype=float)
    closes = w_df['close'].to_numpy(dtype=float)
    ema30 = w_df['ema30'].to_numpy(dtype=float)
    qualifies = w_df['qualifies'].to_numpy(dtype=bool)
    
    trades = []
    state = 'IDLE' # 'IDLE', 'ARMED', 'IN_TRADE'
    armed_high = None
    armed_bar_count = 0
    armed_exit_low = None
    entry_price = None
    entry_date = None
    max_favorable = 0.0
    max_adverse = 0.0
    entry_signals = pd.Series(False, index=df.index)
    
    for i in range(len(w_df)):
        cur_date = dates[i]
        
        # ----------------------------------------------------------------------
        # STATE 1: IN_TRADE (Manage Trailing 30 EMA Breakdown Exit)
        # ----------------------------------------------------------------------
        if state == 'IN_TRADE':
            favorable = (highs[i] - entry_price) / entry_price * 100.0
            adverse = (lows[i] - entry_price) / entry_price * 100.0
            max_favorable = max(max_favorable, favorable)
            max_adverse = min(max_adverse, adverse)
            
            # Rule 3: If previous candle closed below 30 EMA, did current candle break its low?
            if armed_exit_low is not None:
                if lows[i] < armed_exit_low:
                    # Low broken by next candle! Exit triggered!
                    exit_px = armed_exit_low if opens[i] >= armed_exit_low else opens[i]
                    pnl_pct = ((exit_px - entry_price) / entry_price) * 100.0
                    trades.append({
                        'entry_date': entry_date,
                        'entry_price': round(float(entry_price), 2),
                        'exit_date': cur_date,
                        'exit_price': round(float(exit_px), 2),
                        'exit_reason': 'Exit (Close Below 30 EMA & Low Broken)',
                        'pnl_pct': round(float(pnl_pct), 2),
                        'mfe_pct': round(float(max_favorable), 2),
                        'mae_pct': round(float(max_adverse), 2)
                    })
                    state = 'IDLE'
                    armed_exit_low = None
                    entry_price = None
                    continue
                elif closes[i] >= ema30[i]:
                    # Disarmed: Price recovered and closed back above 30 EMA
                    armed_exit_low = None
                elif closes[i] < ema30[i]:
                    # Consecutive candle closed below 30 EMA: trail down armed low
                    armed_exit_low = min(armed_exit_low, lows[i])
                    
            # Check if current candle closes below 30 EMA (arms exit for next candle)
            if closes[i] < ema30[i]:
                armed_exit_low = lows[i]
                
        # ----------------------------------------------------------------------
        # STATE 2: ARMED FOR BREAKOUT
        # ----------------------------------------------------------------------
        elif state == 'ARMED':
            armed_bar_count += 1
            
            # Check if current candle breaks armed_high
            if highs[i] > armed_high:
                # Rule 1: Fundamental check
                fund_ok = True
                if REQUIRE_FUNDAMENTALS:
                    if quarters:
                        fund_ok = is_profit_doubled_as_of(quarters, cur_date)
                    else:
                        fund_ok = False
                        
                if fund_ok:
                    entry_price = armed_high if opens[i] <= armed_high else opens[i]
                    entry_date = cur_date
                    state = 'IN_TRADE'
                    armed_exit_low = None
                    armed_high = None
                    armed_bar_count = 0
                    max_favorable = max(0.0, (highs[i] - entry_price) / entry_price * 100.0)
                    max_adverse = min(0.0, (lows[i] - entry_price) / entry_price * 100.0)
                    
                    dt_ts = pd.to_datetime(cur_date)
                    dt_series = pd.to_datetime(df.index)
                    matched_idx = df.index[dt_series >= dt_ts]
                    if len(matched_idx) > 0:
                        entry_signals.loc[matched_idx[0]] = True
                        
                    if closes[i] < ema30[i]:
                        armed_exit_low = lows[i]
                else:
                    state = 'IDLE'
                    armed_high = None
                    armed_bar_count = 0
            elif qualifies[i]:
                # Subsequent candle also qualifies: update armed high
                armed_high = highs[i]
                armed_bar_count = 0
            elif armed_bar_count > MAX_ARMED_BARS or closes[i] < ema30[i]:
                # Disarmed after timeout or breakdown
                state = 'IDLE'
                armed_high = None
                armed_bar_count = 0
                
        # ----------------------------------------------------------------------
        # STATE 3: IDLE (Looking for qualifying weekly candle)
        # ----------------------------------------------------------------------
        elif state == 'IDLE':
            if qualifies[i]:
                state = 'ARMED'
                armed_high = highs[i]
                armed_bar_count = 0
                
    # If still open at end of data
    if state == 'IN_TRADE':
        pnl_pct = ((closes[-1] - entry_price) / entry_price) * 100.0
        trades.append({
            'entry_date': entry_date,
            'entry_price': round(float(entry_price), 2),
            'exit_date': dates[-1],
            'exit_price': round(float(closes[-1]), 2),
            'exit_reason': 'End of Data (Running)',
            'pnl_pct': round(float(pnl_pct), 2),
            'mfe_pct': round(float(max_favorable), 2),
            'mae_pct': round(float(max_adverse), 2),
            'is_open': True
        })
        
    return {
        'long_entry': entry_signals,
        'tp_pct': 1.0,
        'sl_pct': 0.15,
        'trades': trades
    }

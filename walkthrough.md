# Walkthrough: Fundamental Filters & Continuous Kotak Neo Sync

## Summary of Changes

### 1. Updated Fundamental Criteria for **Weekly Yearly-R1 Breakout Strategy (RSI > 80 + Next Bar Breakout + 100% TP & 30 EMA Trailing Exit)**
Per your instructions, we removed the QoQ increasing constraint while strictly keeping the positive profitability requirement:

#### **Updated Rule**:
- **Profitability Requirement (`Net Profit > 0`)**:
  - The company's Net Profit / Net Income must be strictly positive (`> 0`) for each of the last 2 quarters.
  - Loss-making companies (`Net Profit <= 0`) are disqualified immediately.
- **QoQ Growth Requirement**:
  - **Removed**: Profits do not need to increase quarter-over-quarter. As long as the company is profitable, it qualifies.

#### **Configuration Parameters**:
```python
REQUIRE_PROFITABLE = True             # Strictly require Net Profit to be profitable (> 0)
PROFITABLE_QUARTERS = 2               # Number of recent quarters that must be profitable (> 0)
```

#### **Files Updated**:
- Strategy File: [strategies/weekly_yearly_r1_breakout.py](file:///c:/Stock_Screener/strategies/weekly_yearly_r1_breakout.py)
- Backtest Sandbox Registry: [data/backtest_strategies.json](file:///c:/Stock_Screener/data/backtest_strategies.json)

---

### 2. Validation & Verification
- **Profitable Stocks Allowed**: `TRENT` (profits: ₹519 Cr & ₹400 Cr, positive in both quarters) now passes successfully and generated its valid 100% TP trade.
- **Loss-Making Stocks Rejected**: Companies with negative net profits (e.g. `63MOONS` with recent loss of -₹39.7 Cr) are filtered out immediately.

---

### 3. Kotak Neo Background Data Download Status
- **Process**: `fetch_kotak_history.py --existing-only` (Task `task-608`)
- **Current Progress**: **1,971 / 2,294 stocks** (**~86% Complete**, processing letter **"S"** with ~323 stocks remaining).

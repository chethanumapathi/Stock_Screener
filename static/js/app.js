/**
 * ChethanQuant Stock Screener & Backtester - Client Application
 * Multi-Timeframe Screening, DuckDB Parquet Integration, Corporate Action Adjustments, and Interactive Plotly Charts.
 */

// Application State
const AppState = {
    status: null,
    zerodhaStatus: null,
    dates: [],
    strategies: [], // Screener strategies
    backtestStrategies: [], // Backtest strategies
    currentDate: null,
    selectedSegment: 'nifty50',
    selectedTimeframe: '1d',
    chartTimeframe: '1d',
    watchlistSymbols: [],
    screenerResults: [],
    backtestResults: null,
    backtestFilterDays: new Set(['Mon', 'Tue', 'Wed', 'Thu', 'Fri']),
    backtestFilterMonths: new Set(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']),
    rawBacktestTrades: null,
    rawYearWiseRows: null,
    diagnosticsActive: false,
    currentChartSymbol: 'RELIANCE',
    activeTab: 'screener',
    currentStrategyIdx: 0,
    currentBacktestStrategyIdx: 0,
    allSymbols: []
};

// DOM Elements
const elements = {
    // Nav tabs
    navTabs: document.querySelectorAll('.nav-tab-btn'),
    tabPanes: document.querySelectorAll('.tab-pane'),
    
    // Status badges
    dbStatusPill: document.getElementById('db-status-pill'),
    dbStatusText: document.getElementById('db-status-text'),
    
    // Session summary
    sessionDateSelect: document.getElementById('session-date-select'),
    breadthAdvText: document.getElementById('breadth-adv-text'),
    breadthDecText: document.getElementById('breadth-dec-text'),
    breadthAdvBar: document.getElementById('breadth-adv-bar'),
    breadthDecBar: document.getElementById('breadth-dec-bar'),
    breadthUncBar: document.getElementById('breadth-unc-bar'),
    gainersTableBody: document.getElementById('gainers-table-body'),
    losersTableBody: document.getElementById('losers-table-body'),
    volumeTableBody: document.getElementById('volume-table-body'),
    
    // Screener controls
    savedStrategiesBar: document.getElementById('saved-strategies-bar'),
    savedStrategiesList: document.getElementById('saved-strategies-list'),
    timeframeSelect: document.getElementById('timeframe-select'),
    strategySelect: document.getElementById('strategy-select'),
    strategyNameInput: document.getElementById('strategy-name-input'),
    segmentSelect: document.getElementById('segment-select'),
    watchlistUploadGroup: document.getElementById('watchlist-upload-group'),
    watchlistFileInput: document.getElementById('watchlist-file-input'),
    watchlistInfo: document.getElementById('watchlist-info'),
    screenStartDate: document.getElementById('screen-start-date'),
    screenEndDate: document.getElementById('screen-end-date'),
    minMcapSelect: document.getElementById('min-mcap-select'),
    minMcapInput: document.getElementById('min-mcap-input'),
    codeEditor: document.getElementById('code-editor'),
    btnRunScreener: document.getElementById('btn-run-screener'),
    btnSaveStrategy: document.getElementById('btn-save-strategy'),
    btnDeleteStrategy: document.getElementById('btn-delete-strategy'),
    screenerLoading: document.getElementById('screener-loading'),
    screenerResultsContainer: document.getElementById('screener-results-container'),
    screenerMatchesSummary: document.getElementById('screener-matches-summary'),
    screenerMetaSummary: document.getElementById('screener-meta-summary'),
    resultsTableThead: document.getElementById('results-table-thead'),
    resultsTableBody: document.getElementById('results-table-body'),
    btnExportExcel: document.getElementById('btn-export-excel'),
    btnExportCsv: document.getElementById('btn-export-csv'),
    
    // Backtest Analytics elements
    btCodeEditor: document.getElementById('bt-code-editor'),
    btBtnRunBacktest: document.getElementById('bt-btn-run-backtest'),
    btTimeframeSelect: document.getElementById('bt-timeframe-select'),
    btSegmentSelect: document.getElementById('bt-segment-select'),
    btStrategySelect: document.getElementById('bt-strategy-select'),
    btStrategyNameInput: document.getElementById('bt-strategy-name-input'),
    btBtnSaveStrategy: document.getElementById('bt-btn-save-strategy'),
    btBtnDeleteStrategy: document.getElementById('bt-btn-delete-strategy'),
    btCapitalInput: document.getElementById('bt-capital-input'),
    btScreenStartDate: document.getElementById('bt-screen-start-date'),
    btScreenEndDate: document.getElementById('bt-screen-end-date'),
    btMinMcapSelect: document.getElementById('bt-min-mcap-select'),
    btMinMcapInput: document.getElementById('bt-min-mcap-input'),
    btScreenerLoading: document.getElementById('bt-screener-loading'),
    btTradeLogContainer: document.getElementById('bt-trade-log-container'),
    btTradesCount: document.getElementById('bt-trades-count'),
    btTradesMeta: document.getElementById('bt-trades-meta'),
    btTradesTableBody: document.getElementById('bt-trades-table-body'),
    btBtnExportExcel: document.getElementById('bt-btn-export-excel'),
    btBtnExportPdf: document.getElementById('bt-btn-export-pdf'),
    btBtnExportCsv: document.getElementById('bt-btn-export-csv'),
    btSavedStrategiesBar: document.getElementById('bt-saved-strategies-bar'),
    btSavedStrategiesList: document.getElementById('bt-saved-strategies-list'),
    btReportReadyModal: document.getElementById('bt-report-ready-modal'),
    btnCloseBtReadyModal: document.getElementById('btn-close-bt-ready-modal'),
    btnBtReadyDismiss: document.getElementById('btn-bt-ready-dismiss'),
    btnBtReadyView: document.getElementById('btn-bt-ready-view'),
    btnBtReadyPrint: document.getElementById('btn-bt-ready-print'),
    btReadySubtitle: document.getElementById('bt-ready-subtitle'),
    btReadyNetPnl: document.getElementById('bt-ready-net-pnl'),
    btReadyRoi: document.getElementById('bt-ready-roi'),
    btReadyWinrate: document.getElementById('bt-ready-winrate'),
    btReadyWinLoss: document.getElementById('bt-ready-win-loss'),
    btReadyTrades: document.getElementById('bt-ready-trades'),
    btReadyTradesStatus: document.getElementById('bt-ready-trades-status'),
    btReadyPf: document.getElementById('bt-ready-pf'),
    btReadyMaxdd: document.getElementById('bt-ready-maxdd'),
    btReadyTimeframe: document.getElementById('bt-ready-timeframe'),
    btReadySegment: document.getElementById('bt-ready-segment'),
    btReadyDuration: document.getElementById('bt-ready-duration'),
    btReadyDaterange: document.getElementById('bt-ready-daterange'),

    // Diagnostics Suite Controls
    btnToggleDiagnostics: document.getElementById('btn-toggle-diagnostics'),
    btnToggleDiagnosticsIcon: document.getElementById('btn-toggle-diagnostics-icon'),
    btnToggleDiagnosticsText: document.getElementById('btn-toggle-diagnostics-text'),
    diagStandbyPlaceholder: document.getElementById('diag-standby-placeholder'),
    btnRunDiagnosticsHero: document.getElementById('btn-run-diagnostics-hero'),
    diagMasterTabsWrap: document.getElementById('diag-master-tabs-wrap'),
    diagContentWrapper: document.getElementById('diag-content-wrapper'),

    // GenAI Strategy Template Modal
    scLinkGenaiTemplate: document.getElementById('sc-link-genai-template'),
    btLinkGenaiTemplate: document.getElementById('bt-link-genai-template'),
    genaiTemplateModal: document.getElementById('genai-template-modal'),
    btnCloseGenaiModal: document.getElementById('btn-close-genai-modal'),
    btnCopyGenaiPrompt: document.getElementById('btn-copy-genai-prompt'),
    btnCopyPythonCode: document.getElementById('btn-copy-python-code'),
    textGenaiPrompt: document.getElementById('text-genai-prompt'),
    textPythonCode: document.getElementById('text-python-code'),
    genaiModalTabs: document.querySelectorAll('.modal-tab-btn'),
    genaiModalPanes: document.querySelectorAll('.modal-tab-pane'),

    // Backtest Results Controls (Image 1)
    btToggleBrokerage: document.getElementById('bt-toggle-brokerage'),
    btBrokerageInput: document.getElementById('bt-brokerage-input'),
    btBrokerageVal: document.getElementById('bt-brokerage-val'),
    btBtnEditBrokerage: document.getElementById('bt-btn-edit-brokerage'),
    btToggleTaxes: document.getElementById('bt-toggle-taxes'),
    btTaxesVal: document.getElementById('bt-taxes-val'),
    btBtnTaxesInfo: document.getElementById('bt-btn-taxes-info'),
    btSlippageInput: document.getElementById('bt-slippage-input'),
    btBtnRecalculate: document.getElementById('bt-btn-recalculate'),
    btChipClear: document.getElementById('bt-chip-clear'),
    btChipWeekdays: document.getElementById('bt-chip-weekdays'),
    btDayPills: document.querySelectorAll('.day-pill'),
    btBtnSelectAllMonths: document.getElementById('bt-btn-select-all-months'),
    btBtnClearAllMonths: document.getElementById('bt-btn-clear-all-months'),

    // Year-wise Matrix Table (Image 2)
    btYearWiseTbody: document.getElementById('bt-year-wise-tbody'),

    // Drawdown Chart (Image 3)
    btDrawdownChartContainer: document.getElementById('bt-drawdown-chart-container'),
    btBtnResetDdChart: document.getElementById('bt-btn-reset-dd-chart'),

    // Overall Report Metrics (Image 4)
    metricOverallProfit: document.getElementById('metric-overall-profit'),
    metricCagr: document.getElementById('metric-cagr'),
    metricNoOfTrades: document.getElementById('metric-no-of-trades'),
    metricAvgProfitPerTrade: document.getElementById('metric-avg-profit-per-trade'),
    metricWinPct: document.getElementById('metric-win-pct'),
    metricLossPct: document.getElementById('metric-loss-pct'),
    metricAvgWin: document.getElementById('metric-avg-win'),
    metricAvgLoss: document.getElementById('metric-avg-loss'),
    metricMaxProfit: document.getElementById('metric-max-profit'),
    metricMaxLoss: document.getElementById('metric-max-loss'),
    metricMaxDrawdown: document.getElementById('metric-max-drawdown'),
    metricMddDuration: document.getElementById('metric-mdd-duration'),
    metricReturnMdd: document.getElementById('metric-return-mdd'),
    metricRewardRisk: document.getElementById('metric-reward-risk'),
    metricExpectancy: document.getElementById('metric-expectancy'),
    metricWinStreak: document.getElementById('metric-win-streak'),
    metricLossStreak: document.getElementById('metric-loss-streak'),
    metricTradesInDd: document.getElementById('metric-trades-in-dd'),
    metricProfitFactor: document.getElementById('metric-profit-factor'),
    metricCalmarRatio: document.getElementById('metric-calmar-ratio'),
    metricSharpeRatio: document.getElementById('metric-sharpe-ratio'),
    metricSortinoRatio: document.getElementById('metric-sortino-ratio'),
    metricRecoveryFactor: document.getElementById('metric-recovery-factor'),
    metricUlcerIndex: document.getElementById('metric-ulcer-index'),
    metricPeakCapital: document.getElementById('metric-peak-capital'),
    metricMaxConcurrent: document.getElementById('metric-max-concurrent'),
    metricCapitalUtilization: document.getElementById('metric-capital-utilization'),
    metricSymbolConcentration: document.getElementById('metric-symbol-concentration'),
    metricAvgMae: document.getElementById('metric-avg-mae'),
    metricAvgMfe: document.getElementById('metric-avg-mfe'),
    metricProfitableMonths: document.getElementById('metric-profitable-months'),
    metricTimeUnderWater: document.getElementById('metric-time-under-water'),
    metricAvgHolding: document.getElementById('metric-avg-holding'),
    
    // Technical Chart
    chartSymbolInput: document.getElementById('chart-symbol-input'),
    symbolSuggestionsDropdown: document.getElementById('symbol-suggestions-dropdown'),
    btnLoadChart: document.getElementById('btn-load-chart'),
    chartTimeframeButtons: document.querySelectorAll('.tf-btn'),
    chartSplitAlert: document.getElementById('chart-split-alert'),
    chartSplitDetails: document.getElementById('chart-split-details'),
    quotePrice: document.getElementById('quote-price'),
    quoteChange: document.getElementById('quote-change'),
    quoteVolume: document.getElementById('quote-volume'),
    quoteRange: document.getElementById('quote-range'),
    plotlyContainer: document.getElementById('plotly-chart-container'),
    rawTableContainer: document.getElementById('raw-table-container'),
    rawTableBody: document.getElementById('raw-table-body'),
    
    // Data Manager
    parquetTickersCount: document.getElementById('parquet-tickers-count'),
    parquetSplitsStatus: document.getElementById('parquet-splits-status'),
    btnRefreshSplits: document.getElementById('btn-refresh-splits'),
    btnVerifyParquet: document.getElementById('btn-verify-parquet'),
    rangeSyncStart: document.getElementById('range-sync-start'),
    rangeSyncEnd: document.getElementById('range-sync-end'),
    btnSyncRange: document.getElementById('btn-sync-range'),
    btnExportDb: document.getElementById('btn-export-db'),
    
    // Toasts
    toastContainer: document.getElementById('toast-container')
};

// Toast notification helper
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';
    
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    elements.toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Format numbers nicely
function formatNumber(val) {
    if (val === undefined || val === null || isNaN(val)) return '-';
    return Number(val).toLocaleString('en-IN');
}

// Format dates nicely to DD-MMM-YYYY (e.g. 15-Jan-2024 or 15-Jan-2024 09:15)
function formatDateDDMMMYYYY(val) {
    if (!val || val === '-' || val === 'nan' || val === 'None' || val === 'null' || val === 'undefined') {
        return '-';
    }
    const s = String(val).trim();
    if (!s || s === '-') return '-';

    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    
    // 1. Check if YYYY-MM-DD or YYYY/MM/DD, optionally followed by time
    const isoMatch = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T\s](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
    if (isoMatch) {
        const year = isoMatch[1];
        const month = parseInt(isoMatch[2], 10);
        const day = String(parseInt(isoMatch[3], 10)).padStart(2, '0');
        if (month >= 1 && month <= 12) {
            let res = `${day}-${months[month - 1]}-${year}`;
            if (isoMatch[4] !== undefined && isoMatch[5] !== undefined) {
                const hh = String(parseInt(isoMatch[4], 10)).padStart(2, '0');
                const mm = String(parseInt(isoMatch[5], 10)).padStart(2, '0');
                if (hh !== '00' || mm !== '00') {
                    res += ` ${hh}:${mm}`;
                }
            }
            return res;
        }
    }

    // 2. Check if DD-MM-YYYY or DD/MM/YYYY
    const dmyMatch = s.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?:[T\s](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
    if (dmyMatch) {
        const day = String(parseInt(dmyMatch[1], 10)).padStart(2, '0');
        const month = parseInt(dmyMatch[2], 10);
        const year = dmyMatch[3];
        if (month >= 1 && month <= 12) {
            let res = `${day}-${months[month - 1]}-${year}`;
            if (dmyMatch[4] !== undefined && dmyMatch[5] !== undefined) {
                const hh = String(parseInt(dmyMatch[4], 10)).padStart(2, '0');
                const mm = String(parseInt(dmyMatch[5], 10)).padStart(2, '0');
                if (hh !== '00' || mm !== '00') {
                    res += ` ${hh}:${mm}`;
                }
            }
            return res;
        }
    }

    // 3. Check if already DD-MMM-YYYY or DD MMM YYYY (e.g. 15-Jan-2024 or 15-JAN-2024)
    const dmmmMatch = s.match(/^(\d{1,2})[-/ ]([a-zA-Z]{3,9})[-/ ](\d{4})(?:[T\s](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
    if (dmmmMatch) {
        const day = String(parseInt(dmmmMatch[1], 10)).padStart(2, '0');
        const mStr = dmmmMatch[2].slice(0, 3).toLowerCase();
        const mIdx = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'].indexOf(mStr);
        if (mIdx !== -1) {
            let res = `${day}-${months[mIdx]}-${dmmmMatch[3]}`;
            if (dmmmMatch[4] !== undefined && dmmmMatch[5] !== undefined) {
                const hh = String(parseInt(dmmmMatch[4], 10)).padStart(2, '0');
                const mm = String(parseInt(dmmmMatch[5], 10)).padStart(2, '0');
                if (hh !== '00' || mm !== '00') {
                    res += ` ${hh}:${mm}`;
                }
            }
            return res;
        }
    }

    return s;
}

// Tab Switching
function initTabs() {
    elements.navTabs.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            switchTab(targetTab);
        });
    });

    initQuantSubtabs();
}

function initQuantSubtabs() {
    const btns = document.querySelectorAll('.quant-subtab-btn');
    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            btns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const targetId = btn.getAttribute('data-quant-subtab');
            document.querySelectorAll('.quant-subtab-content').forEach(c => {
                c.style.display = (c.id === targetId) ? 'block' : 'none';
            });
            if (targetId === 'subtab-backtest-analytics' && window.Plotly && elements.btDrawdownChartContainer) {
                setTimeout(() => {
                    try { Plotly.Plots.resize(elements.btDrawdownChartContainer); } catch(e){}
                }, 50);
            }
        });
    });
}

function switchTab(tabId) {
    AppState.activeTab = tabId;
    elements.navTabs.forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
    });
    elements.tabPanes.forEach(p => {
        p.classList.toggle('active', p.id === `tab-${tabId}`);
    });
    
    // If switching to chart tab, resize Plotly chart
    if (tabId === 'chart' && window.Plotly && elements.plotlyContainer) {
        setTimeout(() => {
            Plotly.Plots.resize(elements.plotlyContainer);
        }, 100);
    }
}
window.switchTab = switchTab;

// Initial Data Loaders
async function loadStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        AppState.status = data;
        
        if (data.has_data) {
            if (elements.dbStatusPill) elements.dbStatusPill.classList.remove('loading');
            const count = data.parquet_symbols_count || data.total_symbols;
            if (elements.dbStatusText) elements.dbStatusText.textContent = `● DuckDB: ${formatNumber(count)} Tickers Ready`;
            
            if (data.latest_date) {
                if (elements.screenEndDate) {
                    elements.screenEndDate.value = data.latest_date;
                    elements.screenEndDate.max = data.latest_date;
                }
                if (elements.btScreenEndDate) {
                    elements.btScreenEndDate.value = data.latest_date;
                    elements.btScreenEndDate.max = data.latest_date;
                }
            }
            if (data.oldest_date) {
                if (elements.screenStartDate) elements.screenStartDate.value = data.oldest_date;
                if (elements.btScreenStartDate) elements.btScreenStartDate.value = data.oldest_date;
            }
        } else {
            if (elements.dbStatusPill) elements.dbStatusPill.classList.add('loading');
            if (elements.dbStatusText) elements.dbStatusText.textContent = `● Parquet DB Empty`;
        }
    } catch (err) {
        console.error('Error fetching database status:', err);
    }
}

async function loadZerodhaStatus() {
    try {
        const res = await fetch('/api/zerodha/status');
        const data = await res.json();
        AppState.zerodhaStatus = data;
        
        if (elements.parquetTickersCount) {
            elements.parquetTickersCount.textContent = `${formatNumber(data.total_tickers)} Parquet Files`;
        }
        if (elements.parquetSplitsStatus) {
            elements.parquetSplitsStatus.textContent = `Auto-Adjustment Active (${data.corporate_actions_tracked} Splits Tracked)`;
        }
    } catch (err) {
        console.error('Error fetching Zerodha status:', err);
    }
}

async function loadDates() {
    try {
        const res = await fetch('/api/dates');
        const data = await res.json();
        AppState.dates = data.dates || [];
        
        if (AppState.dates.length > 0) {
            if (elements.sessionDateSelect) {
                elements.sessionDateSelect.innerHTML = '';
                AppState.dates.forEach(d => {
                    const opt = document.createElement('option');
                    opt.value = d;
                    opt.textContent = d;
                    elements.sessionDateSelect.appendChild(opt);
                });
                
                AppState.currentDate = AppState.dates[0];
                elements.sessionDateSelect.value = AppState.currentDate;
                await loadSessionSummary(AppState.currentDate);
            }

            const latestTradingDate = AppState.dates[0];
            if (elements.screenEndDate) {
                elements.screenEndDate.value = latestTradingDate;
                elements.screenEndDate.max = latestTradingDate;
            }
            if (elements.btScreenEndDate) {
                elements.btScreenEndDate.value = latestTradingDate;
                elements.btScreenEndDate.max = latestTradingDate;
            }
            
            const todayStr = new Date().toISOString().split('T')[0];
            if (elements.rangeSyncEnd) {
                elements.rangeSyncEnd.value = todayStr;
                elements.rangeSyncEnd.max = todayStr;
            }
            if (elements.rangeSyncStart) {
                const pastDate = new Date();
                pastDate.setDate(pastDate.getDate() - 30);
                elements.rangeSyncStart.value = pastDate.toISOString().split('T')[0];
                elements.rangeSyncStart.max = todayStr;
            }
        }
    } catch (err) {
        console.error('Error fetching dates:', err);
    }
}

async function loadSessionSummary(dateStr) {
    if (!dateStr || !elements.gainersTableBody) return;
    try {
        const res = await fetch(`/api/session-summary?date=${encodeURIComponent(dateStr)}`);
        const data = await res.json();
        if (data.status === 'ok') {
            renderBreadth(data.breadth, data.total_stocks);
            renderLeaderboards(data);
        }
    } catch (err) {
        console.error('Error loading session summary:', err);
    }
}

function renderBreadth(breadth, total) {
    if (!breadth || total === 0 || !elements.breadthAdvText) return;
    const adv = breadth.advances || 0;
    const dec = breadth.declines || 0;
    const unc = breadth.unchanged || 0;
    
    const advPct = ((adv / total) * 100).toFixed(1);
    const decPct = ((dec / total) * 100).toFixed(1);
    const uncPct = ((unc / total) * 100).toFixed(1);
    
    elements.breadthAdvText.textContent = `${adv} (${advPct}%)`;
    elements.breadthDecText.textContent = `${dec} (${decPct}%)`;
    
    if (elements.breadthAdvBar) elements.breadthAdvBar.style.width = `${advPct}%`;
    if (elements.breadthDecBar) elements.breadthDecBar.style.width = `${decPct}%`;
    if (elements.breadthUncBar) elements.breadthUncBar.style.width = `${uncPct}%`;
}

function renderLeaderboards(data) {
    if (!elements.gainersTableBody) return;
    // Gainers
    elements.gainersTableBody.innerHTML = '';
    (data.top_gainers || []).forEach(item => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><span class="stock-pill stock-copy" title="View ${item.Symbol} Fundamentals" onclick="openFundamentalsModal('${item.Symbol}')">${item.Symbol}</span></td>
            <td style="font-family: var(--font-mono); font-weight: 600;">₹${Number(item.Close).toFixed(2)}</td>
            <td><span class="badge-green">+${Number(item.Pct_Change).toFixed(2)}%</span></td>
            <td style="color: var(--text-muted);">${formatNumber(item.Volume)}</td>
        `;
        elements.gainersTableBody.appendChild(tr);
    });

    // Losers
    elements.losersTableBody.innerHTML = '';
    (data.top_losers || []).forEach(item => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><span class="stock-pill stock-copy" title="View ${item.Symbol} Fundamentals" onclick="openFundamentalsModal('${item.Symbol}')">${item.Symbol}</span></td>
            <td style="font-family: var(--font-mono); font-weight: 600;">₹${Number(item.Close).toFixed(2)}</td>
            <td><span class="badge-red">${Number(item.Pct_Change).toFixed(2)}%</span></td>
            <td style="color: var(--text-muted);">${formatNumber(item.Volume)}</td>
        `;
        elements.losersTableBody.appendChild(tr);
    });

    // Volume
    elements.volumeTableBody.innerHTML = '';
    (data.top_volume || []).forEach(item => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><span class="stock-pill stock-copy" title="View ${item.Symbol} Fundamentals" onclick="openFundamentalsModal('${item.Symbol}')">${item.Symbol}</span></td>
            <td style="font-family: var(--font-mono); font-weight: 600;">₹${Number(item.Close).toFixed(2)}</td>
            <td style="font-weight: 600; color: #a5b4fc;">${formatNumber(item.Volume)}</td>
        `;
        elements.volumeTableBody.appendChild(tr);
    });
}

// =========================================================================
// 1. Stock Screener Strategy Management (Independent)
// =========================================================================

function populateScreenerStrategySelect() {
    if (!elements.strategySelect) return;
    elements.strategySelect.innerHTML = '';
    
    AppState.strategies.forEach((strat, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = strat.name;
        elements.strategySelect.appendChild(opt);
    });
}

async function loadStrategies(targetStrategyName = null) {
    try {
        const res = await fetch('/api/strategies');
        const data = await res.json();
        AppState.strategies = data.strategies || [];
        
        populateScreenerStrategySelect();
        renderSavedStrategiesLinks();
        
        if (AppState.strategies.length > 0) {
            let selectIdx = 0;
            if (targetStrategyName) {
                const foundIdx = AppState.strategies.findIndex(s => 
                    s.name.trim().toLowerCase() === targetStrategyName.trim().toLowerCase()
                );
                if (foundIdx >= 0) selectIdx = foundIdx;
            } else if (AppState.currentStrategyIdx >= 0 && AppState.currentStrategyIdx < AppState.strategies.length) {
                selectIdx = AppState.currentStrategyIdx;
            }
            AppState.currentStrategyIdx = selectIdx;
            if (elements.strategySelect) elements.strategySelect.value = selectIdx;
            selectStrategy(selectIdx);
        }
    } catch (err) {
        console.error('Error fetching screener strategies:', err);
    }
}

function renderSavedStrategiesLinks() {
    if (!elements.savedStrategiesList) return;
    elements.savedStrategiesList.innerHTML = '';
    
    if (AppState.strategies.length === 0) {
        elements.savedStrategiesList.innerHTML = '<span style="font-size: 0.8rem; color: var(--text-dark);">No saved screeners found</span>';
        return;
    }
    
    AppState.strategies.forEach((strat, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `saved-strategy-link ${idx === AppState.currentStrategyIdx ? 'active' : ''}`;
        btn.setAttribute('data-idx', idx);
        btn.innerHTML = `<span class="strategy-link-icon">⚡</span><span>${strat.name}</span>`;
        btn.title = `Click to load "${strat.name}" into Screener`;
        
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            selectStrategy(idx);
            showToast(`Loaded screener "${strat.name}"`, 'info');
            if (elements.codeEditor) elements.codeEditor.focus();
        });
        
        elements.savedStrategiesList.appendChild(btn);
    });
}

function updateActiveStrategyLink(index) {
    if (!elements.savedStrategiesList) return;
    const links = elements.savedStrategiesList.querySelectorAll('.saved-strategy-link');
    links.forEach((link, idx) => {
        link.classList.toggle('active', idx === index);
    });
}

function selectStrategy(index) {
    AppState.currentStrategyIdx = index;
    const strat = AppState.strategies[index];
    if (strat) {
        if (elements.codeEditor) elements.codeEditor.value = strat.code;
        if (elements.strategyNameInput) elements.strategyNameInput.value = strat.name;
        if (elements.strategySelect) elements.strategySelect.value = index;
        updateActiveStrategyLink(index);
    } else {
        if (elements.codeEditor) elements.codeEditor.value = '';
        if (elements.strategyNameInput) elements.strategyNameInput.value = '';
        updateActiveStrategyLink(-1);
    }
}

async function saveCurrentStrategy() {
    const name = elements.strategyNameInput ? elements.strategyNameInput.value.trim() : '';
    const code = elements.codeEditor ? elements.codeEditor.value.trim() : '';
    
    if (!name || !code) {
        showToast('Please provide both a screener name and code', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/strategies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, code })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast(data.message, 'success');
            await loadStrategies(name);
        } else {
            showToast(data.message, 'error');
        }
    } catch (err) {
        showToast(`Error saving screener: ${err.message}`, 'error');
    }
}

async function deleteCurrentStrategy() {
    let name = elements.strategyNameInput ? elements.strategyNameInput.value.trim() : '';
    if (!name && AppState.strategies && AppState.strategies[AppState.currentStrategyIdx]) {
        name = AppState.strategies[AppState.currentStrategyIdx].name;
    }
    if (!name) {
        showToast('No strategy selected to delete', 'error');
        return;
    }
    
    if (!confirm(`Are you sure you want to delete screener "${name}"?`)) return;
    
    try {
        const res = await fetch('/api/strategies', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast(data.message, 'success');
            AppState.currentStrategyIdx = 0;
            await loadStrategies();
        } else {
            showToast(data.message, 'error');
        }
    } catch (err) {
        showToast(`Error deleting screener: ${err.message}`, 'error');
    }
}

// =========================================================================
// 2. Backtest Strategy Management (Completely Decoupled)
// =========================================================================

function populateBacktestStrategySelect() {
    if (!elements.btStrategySelect) return;
    elements.btStrategySelect.innerHTML = '';
    
    AppState.backtestStrategies.forEach((strat, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = strat.name;
        elements.btStrategySelect.appendChild(opt);
    });
}

async function loadBacktestStrategies(targetStrategyName = null) {
    try {
        const res = await fetch('/api/backtest-strategies');
        const data = await res.json();
        AppState.backtestStrategies = data.strategies || [];
        
        populateBacktestStrategySelect();
        renderSavedBacktestsLinks();
        
        if (AppState.backtestStrategies.length > 0) {
            let selectIdx = 0;
            if (targetStrategyName) {
                const foundIdx = AppState.backtestStrategies.findIndex(s => 
                    s.name.trim().toLowerCase() === targetStrategyName.trim().toLowerCase()
                );
                if (foundIdx >= 0) selectIdx = foundIdx;
            } else if (AppState.currentBacktestStrategyIdx >= 0 && AppState.currentBacktestStrategyIdx < AppState.backtestStrategies.length) {
                selectIdx = AppState.currentBacktestStrategyIdx;
            }
            AppState.currentBacktestStrategyIdx = selectIdx;
            if (elements.btStrategySelect) elements.btStrategySelect.value = selectIdx;
            selectBacktestStrategy(selectIdx);
        }
    } catch (err) {
        console.error('Error fetching backtest strategies:', err);
    }
}

function renderSavedBacktestsLinks() {
    if (!elements.btSavedStrategiesList) return;
    elements.btSavedStrategiesList.innerHTML = '';
    
    if (AppState.backtestStrategies.length === 0) {
        elements.btSavedStrategiesList.innerHTML = '<span style="font-size: 0.8rem; color: var(--text-dark);">No saved backtests found</span>';
        return;
    }
    
    AppState.backtestStrategies.forEach((strat, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `saved-strategy-link ${idx === AppState.currentBacktestStrategyIdx ? 'active' : ''}`;
        btn.setAttribute('data-idx', idx);
        btn.innerHTML = `<span class="strategy-link-icon">🎯</span><span>${strat.name}</span>`;
        btn.title = `Click to load "${strat.name}" into Backtester`;
        
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            selectBacktestStrategy(idx);
            showToast(`Loaded backtest strategy "${strat.name}"`, 'info');
            if (elements.btCodeEditor) elements.btCodeEditor.focus();
        });
        
        elements.btSavedStrategiesList.appendChild(btn);
    });
}

function updateActiveBacktestLink(index) {
    if (!elements.btSavedStrategiesList) return;
    const links = elements.btSavedStrategiesList.querySelectorAll('.saved-strategy-link');
    links.forEach((link, idx) => {
        link.classList.toggle('active', idx === index);
    });
}

function selectBacktestStrategy(index) {
    AppState.currentBacktestStrategyIdx = index;
    const strat = AppState.backtestStrategies[index];
    if (strat) {
        if (elements.btCodeEditor) elements.btCodeEditor.value = strat.code;
        if (elements.btStrategyNameInput) elements.btStrategyNameInput.value = strat.name;
        if (elements.btStrategySelect) elements.btStrategySelect.value = index;
        updateActiveBacktestLink(index);
    } else {
        if (elements.btCodeEditor) elements.btCodeEditor.value = '';
        if (elements.btStrategyNameInput) elements.btStrategyNameInput.value = '';
        updateActiveBacktestLink(-1);
    }
}

async function saveCurrentBacktestStrategy() {
    const name = elements.btStrategyNameInput ? elements.btStrategyNameInput.value.trim() : '';
    const code = elements.btCodeEditor ? elements.btCodeEditor.value.trim() : '';
    
    if (!name || !code) {
        showToast('Please provide both a backtest strategy name and code', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/backtest-strategies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, code })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast(data.message, 'success');
            await loadBacktestStrategies(name);
        } else {
            showToast(data.message, 'error');
        }
    } catch (err) {
        showToast(`Error saving backtest strategy: ${err.message}`, 'error');
    }
}

async function deleteCurrentBacktestStrategy() {
    let name = elements.btStrategyNameInput ? elements.btStrategyNameInput.value.trim() : '';
    if (!name && AppState.backtestStrategies && AppState.backtestStrategies[AppState.currentBacktestStrategyIdx]) {
        name = AppState.backtestStrategies[AppState.currentBacktestStrategyIdx].name;
    }
    if (!name) {
        showToast('No backtest strategy selected to delete', 'error');
        return;
    }
    
    if (!confirm(`Are you sure you want to delete backtest strategy "${name}"?`)) return;
    
    try {
        const res = await fetch('/api/backtest-strategies', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast(data.message, 'success');
            AppState.currentBacktestStrategyIdx = 0;
            await loadBacktestStrategies();
        } else {
            showToast(data.message, 'error');
        }
    } catch (err) {
        showToast(`Error deleting backtest strategy: ${err.message}`, 'error');
    }
}

// =========================================================================
// 3. Stock Screener Execution
// =========================================================================

async function runScreener() {
    const code = elements.codeEditor ? elements.codeEditor.value.trim() : '';
    if (!code) {
        showToast('Please enter Python screen(df) function code', 'error');
        return;
    }
    
    const segment = elements.segmentSelect ? elements.segmentSelect.value : 'nifty50';
    const timeframe = elements.timeframeSelect ? elements.timeframeSelect.value : '1d';
    const startDate = elements.screenStartDate ? elements.screenStartDate.value || null : null;
    const endDate = elements.screenEndDate ? elements.screenEndDate.value || null : null;
    const minMcap = elements.minMcapInput ? Number(elements.minMcapInput.value) || 0 : 2000;
    
    if (elements.btnRunScreener) elements.btnRunScreener.disabled = true;
    if (elements.screenerLoading) elements.screenerLoading.style.display = 'block';
    if (elements.screenerResultsContainer) elements.screenerResultsContainer.style.display = 'none';
    
    try {
        const res = await fetch('/api/screen', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: code,
                segment: segment,
                timeframe: timeframe,
                watchlist: AppState.watchlistSymbols,
                start_date: startDate,
                end_date: endDate,
                min_market_cap_cr: minMcap
            })
        });
        
        const data = await res.json();
        
        if (data.status === 'error') {
            showToast(data.message, 'error');
        } else {
            AppState.screenerResults = data.flat_matches || [];
            showToast(`Screening complete: ${data.total_matches} matches on ${timeframe} in ${data.duration_seconds}s`, 'success');
            renderScreenerResults(data);
        }
    } catch (err) {
        showToast(`Failed to execute screener: ${err.message}`, 'error');
    } finally {
        if (elements.btnRunScreener) elements.btnRunScreener.disabled = false;
        if (elements.screenerLoading) elements.screenerLoading.style.display = 'none';
    }
}

function renderScreenerResults(data) {
    if (!elements.screenerResultsContainer) return;
    elements.screenerResultsContainer.style.display = 'block';
    if (elements.screenerMatchesSummary) elements.screenerMatchesSummary.textContent = `${data.total_matches} Matches Found (${data.timeframe.toUpperCase()})`;
    if (elements.screenerMetaSummary) elements.screenerMetaSummary.textContent = `Scanned ${data.total_symbols_scanned} stocks on [${data.timeframe}] across ${data.dates_with_matches} periods in ${data.duration_seconds}s`;
    
    const matches = data.flat_matches || [];
    if (matches.length === 0) {
        if (elements.resultsTableThead) elements.resultsTableThead.innerHTML = `<tr><th>Status</th></tr>`;
        if (elements.resultsTableBody) elements.resultsTableBody.innerHTML = `<tr><td style="text-align: center; color: var(--text-muted); padding: 2rem;">No stocks matched criteria on timeframe ${data.timeframe}.</td></tr>`;
        if (elements.btnExportExcel) elements.btnExportExcel.disabled = true;
        if (elements.btnExportCsv) elements.btnExportCsv.disabled = true;
        return;
    }
    
    if (elements.btnExportExcel) elements.btnExportExcel.disabled = false;
    if (elements.btnExportCsv) elements.btnExportCsv.disabled = false;
    
    const unwantedCols = new Set([
        'avg_volume_20', 'close', 'monthly_r2', 'volume', 'volume_ratio',
        'in_trade', 'stage', 'stop_loss', 'entries', 'signal', 'df', 'data', 'dataframe'
    ]);
    const customKeys = new Set();
    matches.forEach(m => {
        if (m.custom_data) {
            Object.keys(m.custom_data).forEach(k => {
                if (!unwantedCols.has(k.toLowerCase())) {
                    customKeys.add(k);
                }
            });
        }
    });
    const customKeysArr = Array.from(customKeys).sort((a, b) => {
        const aLow = a.toLowerCase();
        const bLow = b.toLowerCase();
        if (aLow.includes('trigger_date')) return -1;
        if (bLow.includes('trigger_date')) return 1;
        if (aLow === 'r2_cross_date') return -1;
        if (bLow === 'r2_cross_date') return 1;
        return a.localeCompare(b);
    });
    
    let thHtml = `
        <tr>
            <th>Date / Time</th>
            <th>Symbol</th>
            <th>Market Cap (Cr)</th>
            <th>Close Price</th>
            <th>Change (%)</th>
    `;
    customKeysArr.forEach(k => {
        const headerName = k.replace(/_/g, ' ');
        thHtml += `<th>${headerName}</th>`;
    });
    thHtml += `<th>Action</th></tr>`;
    if (elements.resultsTableThead) elements.resultsTableThead.innerHTML = thHtml;
    
    if (elements.resultsTableBody) {
        elements.resultsTableBody.innerHTML = '';
        matches.forEach(row => {
            const tr = document.createElement('tr');
            
            let changeBadge = '-';
            if (row.Pct_Change > 0) {
                changeBadge = `<span class="badge-green">+${row.Pct_Change}%</span>`;
            } else if (row.Pct_Change < 0) {
                changeBadge = `<span class="badge-red">${row.Pct_Change}%</span>`;
            } else {
                changeBadge = `<span style="color: var(--text-muted); font-family: var(--font-mono);">${row.Pct_Change}%</span>`;
            }
            
            const mcapDisplay = row.Market_Cap_Cr ? `₹${Number(row.Market_Cap_Cr).toLocaleString('en-IN')} Cr` : '-';
            let rowHtml = `
                <td style="color: var(--text-muted); font-family: var(--font-mono);">${formatDateDDMMMYYYY(row.Date)}</td>
                <td>
                    <div style="display: inline-flex; align-items: center; gap: 0.45rem;">
                        <span class="stock-pill stock-copy" title="Click to copy symbol" onclick="copyStockSymbol('${row.Symbol}')">${row.Symbol}</span>
                        <button class="btn-funda-pill" title="View ${row.Symbol} Fundamentals (P&L, Balance Sheet, Ratios)" onclick="event.stopPropagation(); openFundamentalsModal('${row.Symbol}')">
                            📊 Fundamentals
                        </button>
                    </div>
                </td>
                <td style="font-family: var(--font-mono); color: #34d399; font-weight: 600;">${mcapDisplay}</td>
                <td style="font-family: var(--font-mono); font-weight: 600;">₹${Number(row.Close).toFixed(2)}</td>
                <td>${changeBadge}</td>
            `;
            
            customKeysArr.forEach(k => {
                let val = row.custom_data ? row.custom_data[k] : '-';
                if (k.toLowerCase().includes('date') && val !== '-' && val !== undefined && val !== null) {
                    val = formatDateDDMMMYYYY(val);
                }
                rowHtml += `<td style="font-family: var(--font-mono); color: #c7d2fe;">${val !== undefined ? val : '-'}</td>`;
            });
            
            rowHtml += `
                <td style="white-space: nowrap;">
                    <button class="btn btn-primary btn-sm" title="View Quarterly/Yearly Fundamentals" onclick="event.stopPropagation(); openFundamentalsModal('${row.Symbol}')" style="margin-right: 0.35rem; font-size: 0.76rem; padding: 0.25rem 0.6rem;">
                        📊 Fundamentals
                    </button>
                    <button class="btn btn-secondary btn-sm" title="Copy symbol" onclick="copyStockSymbol('${row.Symbol}')" style="font-size: 0.76rem; padding: 0.25rem 0.6rem;">
                        📋 Copy
                    </button>
                </td>
            `;
            
            tr.innerHTML = rowHtml;
            elements.resultsTableBody.appendChild(tr);
        });
    }
}

async function exportResults(format) {
    if (!AppState.screenerResults || AppState.screenerResults.length === 0) {
        showToast('No results available to export', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/export-results', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                results: AppState.screenerResults,
                format: format
            })
        });
        
        if (!res.ok) throw new Error('Export request failed');
        
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `screener_results_${new Date().toISOString().slice(0, 10)}.${format === 'csv' ? 'csv' : 'xlsx'}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        showToast(`Exported ${AppState.screenerResults.length} records to ${format.toUpperCase()}`, 'success');
    } catch (err) {
        showToast(`Export error: ${err.message}`, 'error');
    }
}

// =========================================================================
// 4. Dedicated Backtester Execution & Institutional Analytics
// =========================================================================

function validateBacktestInput(code) {
    if (!code || !code.trim()) {
        showToast('Please enter Python backtest strategy logic', 'error');
        return false;
    }

    // 1. Long Entry validation
    const hasEntry = /long_entry|entries|buy_signal/i.test(code);
    if (!hasEntry) {
        showToast("Validation Error: Long Entry condition is missing. You must define and return 'long_entry' in your strategy.", 'error');
        return false;
    }

    // 2. Target Profit (TP) validation
    const hasTP = /tp_pct|target_profit_pct|\btp\b|target_profit|target_pct/i.test(code);
    if (!hasTP) {
        showToast("Validation Error: Target Profit (TP) is missing. Please define TP (e.g. tp_pct = 0.04 or 'tp_pct' in return dict).", 'error');
        return false;
    }

    // 3. Stop Loss (SL) validation
    const hasSL = /sl_pct|stop_loss_pct|\bsl\b|stop_loss|stop_pct/i.test(code);
    if (!hasSL) {
        showToast("Validation Error: Stop Loss (SL) is missing. Please define SL (e.g. sl_pct = 0.02 or 'sl_pct' in return dict).", 'error');
        return false;
    }

    return true;
}

async function runBacktest() {
    const code = elements.btCodeEditor ? elements.btCodeEditor.value.trim() : '';
    if (!validateBacktestInput(code)) {
        return;
    }

    const segment = elements.btSegmentSelect ? elements.btSegmentSelect.value : 'nifty50';
    const timeframe = elements.btTimeframeSelect ? elements.btTimeframeSelect.value : '1d';
    const capital = elements.btCapitalInput ? Number(elements.btCapitalInput.value) || 100000 : 100000;
    const startDate = elements.btScreenStartDate ? elements.btScreenStartDate.value || null : null;
    const endDate = elements.btScreenEndDate ? elements.btScreenEndDate.value || null : null;
    const slippage = elements.btSlippageInput ? Number(elements.btSlippageInput.value) || 0.5 : 0.5;
    const incBrokerage = elements.btToggleBrokerage ? elements.btToggleBrokerage.checked : true;
    const incTaxes = elements.btToggleTaxes ? elements.btToggleTaxes.checked : true;
    const brokerageVal = elements.btBrokerageInput ? Number(elements.btBrokerageInput.value) || 20 : 20;
    const btMinMcap = elements.btMinMcapInput ? Number(elements.btMinMcapInput.value) || 0 : 2000;

    if (elements.btBtnRunBacktest) elements.btBtnRunBacktest.disabled = true;
    if (elements.btScreenerLoading) elements.btScreenerLoading.style.display = 'block';
    if (elements.btTradeLogContainer) elements.btTradeLogContainer.style.display = 'none';
    resetDiagnosticsUI();

    try {
        const res = await fetch('/api/backtest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: code,
                segment: segment,
                timeframe: timeframe,
                watchlist: AppState.watchlistSymbols,
                start_date: startDate,
                end_date: endDate,
                capital_per_trade: capital,
                slippage_pct: slippage,
                include_brokerage: incBrokerage,
                include_taxes: incTaxes,
                brokerage_per_order: brokerageVal,
                min_market_cap_cr: btMinMcap
            })
        });

        const data = await res.json();
        if (data.status === 'error') {
            showToast(data.message, 'error');
        } else {
            AppState.backtestResults = data;
            AppState.rawBacktestTrades = (data.trades && Array.isArray(data.trades)) ? [...data.trades] : [];
            showToast(`Backtest complete: ${data.total_trades} trades on ${timeframe} in ${data.duration_seconds}s`, 'success');
            renderBacktestResults(data);
            showBacktestReadyModal(data);
        }
    } catch (err) {
        showToast(`Failed to execute backtest: ${err.message}`, 'error');
    } finally {
        if (elements.btBtnRunBacktest) elements.btBtnRunBacktest.disabled = false;
        if (elements.btScreenerLoading) elements.btScreenerLoading.style.display = 'none';
    }
}

function isEndOfDataTrade(t) {
    if (!t) return false;
    if (t.is_open === true || t.is_open === 'true') return true;
    const r = String(t.exit_reason || '').trim().toLowerCase();
    if (r.includes('end of data') || (r.includes('end') && r.includes('data')) || r.includes('running')) return true;
    const d = String(t.duration || '').trim().toLowerCase();
    if (d.includes('running')) return true;
    if (t.net_pnl === null || t.net_pnl === undefined) return true;
    return false;
}

function renderBacktestResults(data) {
    if (!elements.btTradeLogContainer) return;
    elements.btTradeLogContainer.style.display = 'block';

    const trades = data.trades || [];
    const openTradesCount = trades.filter(isEndOfDataTrade).length;
    const closedTradesCount = trades.length - openTradesCount;

    if (elements.btTradesCount) {
        if (openTradesCount > 0) {
            elements.btTradesCount.textContent = `${closedTradesCount} Closed Trades | ${openTradesCount} Running`;
        } else {
            elements.btTradesCount.textContent = `${trades.length} Trades Executed`;
        }
    }
    if (elements.btTradesMeta) elements.btTradesMeta.textContent = `Simulation on ${data.timeframe.toUpperCase()} | Capital ₹${formatNumber(elements.btCapitalInput ? elements.btCapitalInput.value : 100000)} / trade`;

    // 1. Render Trade Log Table
    if (elements.btTradesTableBody) {
        elements.btTradesTableBody.innerHTML = '';
        if (trades.length === 0) {
            elements.btTradesTableBody.innerHTML = `<tr><td colspan="12" style="text-align: center; color: var(--text-muted); padding: 2rem;">No trades generated matching this strategy criteria.</td></tr>`;
        } else {
            trades.forEach(t => {
                const tr = document.createElement('tr');
                
                let reasonBadge = '';
                const isEndOfData = isEndOfDataTrade(t);
                if (isEndOfData) {
                    reasonBadge = `<span style="background: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.35); padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600;">⏳ End of Data (Running)</span>`;
                } else if (t.exit_reason && t.exit_reason.includes('Target')) {
                    reasonBadge = `<span class="badge-green">🎯 ${t.exit_reason}</span>`;
                } else if (t.exit_reason && t.exit_reason.includes('Stop')) {
                    reasonBadge = `<span class="badge-red">🛑 ${t.exit_reason}</span>`;
                } else {
                    reasonBadge = `<span style="background: rgba(99, 102, 241, 0.15); color: #a5b4fc; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">${t.exit_reason || 'Exit'}</span>`;
                }

                let pnlDisplay = '-';
                let pnlPctDisplay = '-';
                let pnlClass = 'text-neutral';

                if (isEndOfData || t.net_pnl === null || t.net_pnl === undefined) {
                    pnlDisplay = `<span style="color: var(--text-muted); font-weight: 500;">-</span>`;
                    pnlPctDisplay = `<span style="color: var(--text-muted); font-weight: 500;">-</span>`;
                } else {
                    pnlClass = t.net_pnl > 0 ? 'text-green' : (t.net_pnl < 0 ? 'text-red' : 'text-neutral');
                    let pnlSign = t.net_pnl > 0 ? '+' : '';
                    let pnlPctSign = t.pnl_pct > 0 ? '+' : '';
                    pnlDisplay = `${pnlSign}₹${Number(t.net_pnl).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                    pnlPctDisplay = `${pnlPctSign}${Number(t.pnl_pct).toFixed(2)}%`;
                }

                const exitPriceDisplay = isEndOfData 
                    ? `<span style="color: var(--text-muted); font-size: 0.85rem;" title="Last Close Price (Still Running)">₹${Number(t.exit_price).toFixed(2)}</span>`
                    : `₹${Number(t.exit_price).toFixed(2)}`;

                tr.innerHTML = `
                    <td style="font-family: var(--font-mono); color: var(--text-dark);">${t.trade_id}</td>
                    <td>
                        <div style="display: inline-flex; align-items: center; gap: 0.45rem;">
                            <span class="stock-pill stock-copy" title="Click to copy symbol" onclick="copyStockSymbol('${t.symbol}')">${t.symbol}</span>
                            <button class="btn-funda-pill" title="View ${t.symbol} Fundamentals (P&L, Balance Sheet, Ratios)" onclick="event.stopPropagation(); openFundamentalsModal('${t.symbol}')">
                                📊 Fundamentals
                            </button>
                        </div>
                    </td>
                    <td><span class="badge-green">Long</span></td>
                    <td style="font-family: var(--font-mono); color: #a5b4fc;">${formatDateDDMMMYYYY(t.trigger_date)}</td>
                    <td style="font-family: var(--font-mono); color: var(--text-muted);">${formatDateDDMMMYYYY(t.entry_date)}</td>
                    <td style="font-family: var(--font-mono); font-weight: 600;">₹${Number(t.entry_price).toFixed(2)}</td>
                    <td style="font-family: var(--font-mono); color: var(--text-muted);">${formatDateDDMMMYYYY(t.exit_date)}</td>
                    <td style="font-family: var(--font-mono); font-weight: 600;">${exitPriceDisplay}</td>
                    <td>${reasonBadge}</td>
                    <td style="font-family: var(--font-mono); font-weight: 700;" class="${pnlClass}">${pnlDisplay}</td>
                    <td style="font-family: var(--font-mono); font-weight: 600;" class="${pnlClass}">${pnlPctDisplay}</td>
                    <td style="font-family: var(--font-mono); color: #c7d2fe;">${t.duration}</td>
                `;
                elements.btTradesTableBody.appendChild(tr);
            });
        }
    }

    // 2. Render Backtest Results Controls (Image 1)
    if (data.summary) {
        if (elements.btBrokerageVal) {
            elements.btBrokerageVal.textContent = `₹ ${Number(data.summary.total_brokerage).toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`;
        }
        if (elements.btTaxesVal) {
            elements.btTaxesVal.textContent = `₹ ${Number(data.summary.total_taxes).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        }
        if (elements.btSlippageInput && data.summary.slippage_pct !== undefined) {
            elements.btSlippageInput.value = data.summary.slippage_pct;
        }
    }

    // 3. Render Year-wise Returns Matrix Table (Image 2)
    renderYearWiseTable(data.year_wise_returns || []);

    // 4. Render Underwater Drawdown Chart (Image 3)
    renderDrawdownChart(data.drawdown_chart || { dates: [], drawdowns: [] });

    // 5. Render Overall Report
    renderOverallReport(data.overall_report || {});

    // 6. Institutional Quantitative Diagnostics & Robustness Suite (deferred on-demand)
    if (data.diagnostics && Object.keys(data.diagnostics).length > 0) {
        AppState.diagnosticsActive = true;
        if (elements.diagStandbyPlaceholder) elements.diagStandbyPlaceholder.style.display = 'none';
        if (elements.diagContentWrapper) elements.diagContentWrapper.style.display = 'block';
        if (elements.diagMasterTabsWrap) elements.diagMasterTabsWrap.style.display = 'flex';
        if (elements.btnToggleDiagnostics) elements.btnToggleDiagnostics.classList.add('btn-active-diag');
        if (elements.btnToggleDiagnosticsIcon) elements.btnToggleDiagnosticsIcon.textContent = '✅';
        if (elements.btnToggleDiagnosticsText) elements.btnToggleDiagnosticsText.textContent = 'Diagnostics Active (Toggle)';
        renderDiagnosticsSuite(data.diagnostics);
    } else {
        resetDiagnosticsUI();
    }
}

function renderYearWiseTable(rows) {
    if (!elements.btYearWiseTbody) return;
    elements.btYearWiseTbody.innerHTML = '';
    AppState.rawYearWiseRows = rows || [];

    // Synchronize header checkboxes with AppState.backtestFilterMonths
    document.querySelectorAll('.bt-month-cb').forEach(cb => {
        const m = cb.getAttribute('data-month');
        const isInc = AppState.backtestFilterMonths ? AppState.backtestFilterMonths.has(m) : true;
        cb.checked = isInc;
        const header = cb.closest('.bt-month-header');
        if (header) {
            header.classList.toggle('excluded', !isInc);
        }
    });

    if (!rows || rows.length === 0) {
        elements.btYearWiseTbody.innerHTML = `<tr><td colspan="17" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No yearly return metrics available.</td></tr>`;
        return;
    }

    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    rows.forEach(r => {
        const tr = document.createElement('tr');
        
        let mHtml = '';
        let activeRowTotal = 0.0;
        months.forEach(m => {
            const isInc = AppState.backtestFilterMonths ? AppState.backtestFilterMonths.has(m) : true;
            const val = Number(r[m]) || 0;
            if (isInc) {
                activeRowTotal += val;
            }
            let cls = val > 0 ? 'text-green' : (val < 0 ? 'text-red' : 'text-neutral');
            if (!isInc) {
                cls += ' month-excluded';
            }
            mHtml += `<td class="${cls}">${val === 0 ? '0' : Number(val).toLocaleString('en-IN')}</td>`;
        });

        activeRowTotal = Math.round(activeRowTotal * 100) / 100;
        const totalCls = activeRowTotal > 0 ? 'text-green' : (activeRowTotal < 0 ? 'text-red' : 'text-neutral');
        const mddCls = r.max_drawdown < 0 ? 'text-red' : 'text-neutral';

        const baseCap = (AppState.backtestResults && AppState.backtestResults.overall_report && AppState.backtestResults.overall_report.peak_capital_deployed) || (AppState.rawBacktestSummary && AppState.rawBacktestSummary.base_capital) || 100000;
        let cagrVal = 0.0;
        if (r.cagr !== undefined && r.cagr !== null) {
            cagrVal = Number(r.cagr);
        } else if (baseCap > 0) {
            cagrVal = Math.round((activeRowTotal / baseCap) * 10000) / 100;
        }
        const cagrCls = cagrVal > 0 ? 'text-green' : (cagrVal < 0 ? 'text-red' : 'text-neutral');
        const cagrStr = `${cagrVal >= 0 ? '+' : ''}${cagrVal.toFixed(2)}%`;

        tr.innerHTML = `
            <td><strong>${r.year}</strong></td>
            ${mHtml}
            <td class="${totalCls}" style="font-weight: 700;">${Number(activeRowTotal).toLocaleString('en-IN')}</td>
            <td class="${mddCls}">${Number(r.max_drawdown).toLocaleString('en-IN')}</td>
            <td style="color: var(--text-dark); font-size: 0.8rem;">${r.days_for_mdd}</td>
            <td class="${cagrCls}" style="font-weight: 700; font-family: var(--font-mono);">${cagrStr}</td>
        `;
        elements.btYearWiseTbody.appendChild(tr);
    });
}

/**
 * Instant in-place recalculation of Year-wise table Total column.
 * Simply adds or subtracts the month numbers in the browser in 0ms without server requests.
 */
function updateYearWiseTableTotals() {
    if (!elements.btYearWiseTbody) return;
    const trs = elements.btYearWiseTbody.querySelectorAll('tr');
    if (!trs || trs.length === 0) return;

    const rows = AppState.rawYearWiseRows;
    if (!rows || rows.length === 0) return;

    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const baseCap = (AppState.backtestResults && AppState.backtestResults.overall_report && AppState.backtestResults.overall_report.peak_capital_deployed) || (AppState.rawBacktestSummary && AppState.rawBacktestSummary.base_capital) || 100000;

    trs.forEach((tr, idx) => {
        const r = rows[idx];
        if (!r) return;

        let activeRowTotal = 0.0;
        months.forEach((m, mIdx) => {
            const isInc = AppState.backtestFilterMonths ? AppState.backtestFilterMonths.has(m) : true;
            // Month cells start at cell 1 (cell 0 is Year)
            const cell = tr.cells[mIdx + 1];
            if (cell) {
                cell.classList.toggle('month-excluded', !isInc);
            }
            if (isInc) {
                activeRowTotal += (Number(r[m]) || 0.0);
            }
        });

        activeRowTotal = Math.round(activeRowTotal * 100) / 100;

        // Total cell (cell index 13)
        const totalCell = tr.cells[13];
        if (totalCell) {
            const totalCls = activeRowTotal > 0 ? 'text-green' : (activeRowTotal < 0 ? 'text-red' : 'text-neutral');
            totalCell.className = `${totalCls}`;
            totalCell.style.fontWeight = '700';
            totalCell.textContent = Number(activeRowTotal).toLocaleString('en-IN');
        }

        // CAGR cell (cell index 16)
        const cagrCell = tr.cells[16];
        if (cagrCell) {
            const cagrVal = baseCap > 0 ? Math.round((activeRowTotal / baseCap) * 10000) / 100 : 0.0;
            const cagrCls = cagrVal > 0 ? 'text-green' : (cagrVal < 0 ? 'text-red' : 'text-neutral');
            cagrCell.className = cagrCls;
            cagrCell.style.fontWeight = '700';
            cagrCell.style.fontFamily = 'var(--font-mono)';
            cagrCell.textContent = `${cagrVal >= 0 ? '+' : ''}${cagrVal.toFixed(2)}%`;
        }
    });
}

function renderDrawdownChart(chartData) {
    if (!elements.btDrawdownChartContainer) return;
    
    const dates = chartData.dates || [];
    const drawdowns = chartData.drawdowns || [];

    if (dates.length === 0) {
        elements.btDrawdownChartContainer.innerHTML = '<div style="text-align: center; padding: 4rem; color: var(--text-muted);">No drawdown data to plot.</div>';
        return;
    }

    const trace = {
        x: dates,
        y: drawdowns,
        type: 'scatter',
        mode: 'lines',
        line: {
            color: '#ef4444',
            width: 2
        },
        fill: 'tozeroy',
        fillcolor: 'rgba(239, 68, 68, 0.1)',
        name: 'Drawdown'
    };

    const layout = {
        margin: { t: 20, r: 20, l: 60, b: 40 },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        xaxis: {
            gridcolor: 'rgba(255, 255, 255, 0.06)',
            tickfont: { color: '#94a3b8', family: 'Outfit, sans-serif' },
            tickformat: '%d-%b-%Y',
            hoverformat: '%d-%b-%Y',
            showgrid: true
        },
        yaxis: {
            title: 'Drawdown (₹)',
            titlefont: { color: '#94a3b8', size: 12 },
            gridcolor: 'rgba(255, 255, 255, 0.06)',
            tickfont: { color: '#94a3b8', family: 'JetBrains Mono, monospace' },
            showgrid: true,
            zeroline: true,
            zerolinecolor: 'rgba(255, 255, 255, 0.2)'
        },
        hovermode: 'x unified'
    };

    const config = {
        responsive: true,
        displayModeBar: false
    };

    Plotly.newPlot(elements.btDrawdownChartContainer, [trace], layout, config);
}

function renderOverallReport(rep) {
    const formatRupee = (val) => {
        if (val === undefined || val === null) return '₹ 0.00';
        const sign = val < 0 ? '-₹ ' : '₹ ';
        return `${sign}${Math.abs(Number(val)).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };

    // Column 1: Returns & Win Rates
    if (elements.metricOverallProfit) {
        elements.metricOverallProfit.textContent = formatRupee(rep.overall_profit);
        elements.metricOverallProfit.className = `cell-val ${rep.overall_profit >= 0 ? 'text-green' : 'text-red'}`;
    }
    if (elements.metricCagr) {
        const cagr = Number(rep.cagr_pct || 0);
        elements.metricCagr.textContent = `${cagr >= 0 ? '+' : ''}${cagr.toFixed(2)}%`;
        elements.metricCagr.className = `cell-val ${cagr >= 0 ? 'text-green' : 'text-red'}`;
    }
    if (elements.metricNoOfTrades) {
        if (rep.open_trades && rep.open_trades > 0) {
            elements.metricNoOfTrades.textContent = `${rep.no_of_trades} (${rep.open_trades} open)`;
        } else {
            elements.metricNoOfTrades.textContent = rep.no_of_trades || 0;
        }
    }
    if (elements.metricWinPct) {
        const winCount = rep.win_trades !== undefined ? rep.win_trades : Math.round(((rep.win_pct || 0) / 100) * (rep.no_of_trades || 0));
        const winPct = Number(rep.win_pct || 0).toFixed(2);
        elements.metricWinPct.textContent = `${winCount} (${winPct}%)`;
        elements.metricWinPct.className = 'cell-val text-green';
    }
    if (elements.metricLossPct) {
        const lossCount = rep.loss_trades !== undefined ? rep.loss_trades : Math.round(((rep.loss_pct || 0) / 100) * (rep.no_of_trades || 0));
        const lossPct = Number(rep.loss_pct || 0).toFixed(2);
        elements.metricLossPct.textContent = `${lossCount} (${lossPct}%)`;
        elements.metricLossPct.className = 'cell-val text-red';
    }
    if (elements.metricAvgProfitPerTrade) {
        elements.metricAvgProfitPerTrade.textContent = formatRupee(rep.avg_profit_per_trade);
        elements.metricAvgProfitPerTrade.className = `cell-val ${rep.avg_profit_per_trade >= 0 ? 'text-green' : 'text-red'}`;
    }
    if (elements.metricAvgWin) elements.metricAvgWin.textContent = formatRupee(rep.avg_profit_on_winning);

    // Column 2: Risk-Adjusted Ratios
    if (elements.metricProfitFactor) {
        const pf = Number(rep.profit_factor || 0);
        elements.metricProfitFactor.textContent = pf.toFixed(2);
        elements.metricProfitFactor.className = `cell-val ${pf >= 1.5 ? 'text-green' : (pf < 1.0 ? 'text-red' : 'text-neutral')}`;
    }
    if (elements.metricCalmarRatio) {
        const calmar = Number(rep.calmar_ratio || 0);
        elements.metricCalmarRatio.textContent = calmar.toFixed(2);
        elements.metricCalmarRatio.className = `cell-val ${calmar >= 1.0 ? 'text-green' : 'text-neutral'}`;
    }
    if (elements.metricSharpeRatio) {
        const sharpe = Number(rep.sharpe_ratio || 0);
        elements.metricSharpeRatio.textContent = sharpe.toFixed(2);
        elements.metricSharpeRatio.className = `cell-val ${sharpe >= 1.0 ? 'text-green' : (sharpe < 0 ? 'text-red' : 'text-neutral')}`;
    }
    if (elements.metricSortinoRatio) {
        const sortino = Number(rep.sortino_ratio || 0);
        elements.metricSortinoRatio.textContent = sortino.toFixed(2);
        elements.metricSortinoRatio.className = `cell-val ${sortino >= 1.5 ? 'text-green' : (sortino < 0 ? 'text-red' : 'text-neutral')}`;
    }
    if (elements.metricRewardRisk) elements.metricRewardRisk.textContent = Number(rep.reward_to_risk_ratio || 0).toFixed(2);
    if (elements.metricExpectancy) elements.metricExpectancy.textContent = Number(rep.expectancy_ratio || 0).toFixed(2);
    if (elements.metricReturnMdd) elements.metricReturnMdd.textContent = Number(rep.return_over_max_dd || 0).toFixed(2);
    if (elements.metricRecoveryFactor) {
        const rf = Number(rep.recovery_factor || 0);
        elements.metricRecoveryFactor.textContent = `${rf.toFixed(2)}x`;
        elements.metricRecoveryFactor.className = `cell-val ${rf >= 3.0 ? 'text-green' : 'text-neutral'}`;
    }
    if (elements.metricUlcerIndex) {
        const ui = Number(rep.ulcer_index || 0);
        elements.metricUlcerIndex.textContent = ui.toFixed(2);
        elements.metricUlcerIndex.className = `cell-val ${ui < 10.0 ? 'text-green' : (ui > 20.0 ? 'text-red' : 'text-neutral')}`;
    }
    if (elements.metricMaxDrawdown) elements.metricMaxDrawdown.textContent = formatRupee(rep.max_drawdown);

    // Column 3: Capital & Exposure
    if (elements.metricPeakCapital) {
        elements.metricPeakCapital.textContent = formatRupee(rep.peak_capital_deployed || 100000);
    }
    if (elements.metricMaxConcurrent) {
        elements.metricMaxConcurrent.textContent = `${rep.max_concurrent_positions || 1} pos`;
    }
    if (elements.metricCapitalUtilization) {
        elements.metricCapitalUtilization.textContent = `${Number(rep.capital_utilization_pct || 0).toFixed(1)}%`;
    }
    if (elements.metricSymbolConcentration) {
        elements.metricSymbolConcentration.textContent = rep.symbol_concentration_str || '-';
        if (rep.symbol_concentration_details && rep.symbol_concentration_details !== '-') {
            elements.metricSymbolConcentration.title = rep.symbol_concentration_details;
        }
    }
    if (elements.metricTradesInDd) elements.metricTradesInDd.textContent = rep.max_trades_in_drawdown || 0;
    if (elements.metricMaxProfit) elements.metricMaxProfit.textContent = formatRupee(rep.max_profit_single);
    if (elements.metricMaxLoss) elements.metricMaxLoss.textContent = formatRupee(rep.max_loss_single);
    if (elements.metricMddDuration) elements.metricMddDuration.textContent = rep.duration_of_max_drawdown || '-';

    // Column 4: Trade Quality & Consistency
    if (elements.metricAvgMae) {
        elements.metricAvgMae.textContent = `-${Number(rep.avg_mae_pct || 0).toFixed(2)}%`;
    }
    if (elements.metricAvgMfe) {
        elements.metricAvgMfe.textContent = `+${Number(rep.avg_mfe_pct || 0).toFixed(2)}%`;
    }
    if (elements.metricProfitableMonths) {
        elements.metricProfitableMonths.textContent = rep.profitable_months_str || '-';
        const pmPct = Number(rep.profitable_months_pct || 0);
        elements.metricProfitableMonths.className = `cell-val ${pmPct >= 50 ? 'text-green' : 'text-neutral'}`;
    }
    if (elements.metricTimeUnderWater) {
        const tuw = Number(rep.time_under_water_pct || 0);
        elements.metricTimeUnderWater.textContent = `${tuw.toFixed(1)}%`;
        elements.metricTimeUnderWater.className = `cell-val ${tuw < 50.0 ? 'text-green' : 'text-neutral'}`;
    }
    if (elements.metricAvgHolding) {
        elements.metricAvgHolding.textContent = rep.avg_holding_str || '-';
    }
    if (elements.metricAvgLoss) elements.metricAvgLoss.textContent = formatRupee(rep.avg_loss_on_losing);
    if (elements.metricWinStreak) elements.metricWinStreak.textContent = rep.max_win_streak || 0;
    if (elements.metricLossStreak) elements.metricLossStreak.textContent = rep.max_losing_streak || 0;
}

async function recalculateBacktest() {
    const rawTrades = AppState.rawBacktestTrades || (AppState.backtestResults && AppState.backtestResults.trades);
    if (!rawTrades || rawTrades.length === 0) {
        return;
    }

    const slippage = elements.btSlippageInput ? Number(elements.btSlippageInput.value) || 0 : 0.5;
    const incBrokerage = elements.btToggleBrokerage ? elements.btToggleBrokerage.checked : true;
    const incTaxes = elements.btToggleTaxes ? elements.btToggleTaxes.checked : true;
    const brokerageVal = elements.btBrokerageInput ? Number(elements.btBrokerageInput.value) || 0 : 20.0;
    const weekdaysArr = Array.from(AppState.backtestFilterDays);
    const monthsArr = AppState.backtestFilterMonths ? Array.from(AppState.backtestFilterMonths) : null;

    try {
        const res = await fetch('/api/backtest/recalculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                trades: rawTrades,
                capital_per_trade: elements.btCapitalInput ? Number(elements.btCapitalInput.value) || 100000 : 100000,
                slippage_pct: slippage,
                include_brokerage: incBrokerage,
                include_taxes: incTaxes,
                brokerage_per_order: brokerageVal,
                weekdays: weekdaysArr,
                months: monthsArr
            })
        });

        const data = await res.json();
        if (data.status === 'success') {
            AppState.backtestResults = {
                ...AppState.backtestResults,
                ...data
            };
            renderBacktestResults({
                timeframe: AppState.backtestResults.timeframe || '1d',
                ...data
            });
            showToast('Recalculated backtest results with updated filters', 'info');
        }
    } catch (err) {
        showToast(`Failed to recalculate: ${err.message}`, 'error');
    }
}

async function exportBacktestTrades(format = 'excel') {
    if (!AppState.backtestResults || !AppState.backtestResults.trades || AppState.backtestResults.trades.length === 0) {
        showToast('No backtest trades available to export', 'error');
        return;
    }

    const strategyName = (elements.btStrategyNameInput && elements.btStrategyNameInput.value.trim()) 
        || (AppState.backtestStrategies[AppState.currentBacktestStrategyIdx]?.name) 
        || 'Backtest_Trades';
    const safeName = strategyName.replace(/[\\/*?:"<>|]/g, '_').trim();
    const trades = AppState.backtestResults.trades;

    if (format === 'csv') {
        const headers = [
            'Trade #', 'Symbol', 'Type', 'Trigger Date', 'Entry Date', 'Entry Price (₹)',
            'Exit Date', 'Exit Price (₹)', 'Exit Reason', 'Quantity',
            'Turnover (₹)', 'Gross PnL (₹)', 'Brokerage (₹)', 'Taxes (₹)',
            'Net PnL (₹)', 'PnL (%)', 'Duration', 'Weekday'
        ];
        const rows = trades.map(t => {
            const isEndOfData = isEndOfDataTrade(t);
            return [
                t.trade_id,
                t.symbol,
                t.type,
                `"${formatDateDDMMMYYYY(t.trigger_date)}"`,
                formatDateDDMMMYYYY(t.entry_date),
                t.entry_price,
                formatDateDDMMMYYYY(t.exit_date),
                t.exit_price,
                `"${isEndOfData ? 'End of Data' : (t.exit_reason || 'End of Data')}"`,
                t.qty,
                isEndOfData ? '-' : ((t.turnover !== undefined && t.turnover !== null) ? t.turnover : '-'),
                isEndOfData ? '-' : ((t.gross_pnl !== undefined && t.gross_pnl !== null) ? t.gross_pnl : '-'),
                isEndOfData ? '-' : ((t.brokerage !== undefined && t.brokerage !== null) ? t.brokerage : '-'),
                isEndOfData ? '-' : ((t.taxes !== undefined && t.taxes !== null) ? t.taxes : '-'),
                isEndOfData ? '-' : ((t.net_pnl !== undefined && t.net_pnl !== null) ? t.net_pnl : '-'),
                isEndOfData ? '-' : ((t.pnl_pct !== undefined && t.pnl_pct !== null) ? t.pnl_pct : '-'),
                `"${t.duration || 'Running'}"`,
                t.weekday || ''
            ];
        });
        const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${safeName}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        showToast(`Exported ${trades.length} trades to CSV`, 'success');
    } else {
        try {
            const res = await fetch('/api/export-results', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    strategy_name: strategyName,
                    results: trades.map(t => {
                        const isEndOfData = isEndOfDataTrade(t);
                        return {
                            'Trade #': t.trade_id,
                            'Symbol': t.symbol,
                            'Type': t.type,
                            'Trigger Date': formatDateDDMMMYYYY(t.trigger_date),
                            'Entry Date': formatDateDDMMMYYYY(t.entry_date),
                            'Entry Price (₹)': t.entry_price,
                            'Exit Date': formatDateDDMMMYYYY(t.exit_date),
                            'Exit Price (₹)': t.exit_price,
                            'Exit Reason': isEndOfData ? 'End of Data' : (t.exit_reason || 'End of Data'),
                            'Quantity': t.qty,
                            'Turnover (₹)': isEndOfData ? '-' : ((t.turnover !== undefined && t.turnover !== null) ? t.turnover : '-'),
                            'Gross PnL (₹)': isEndOfData ? '-' : ((t.gross_pnl !== undefined && t.gross_pnl !== null) ? t.gross_pnl : '-'),
                            'Brokerage (₹)': isEndOfData ? '-' : ((t.brokerage !== undefined && t.brokerage !== null) ? t.brokerage : '-'),
                            'Taxes (₹)': isEndOfData ? '-' : ((t.taxes !== undefined && t.taxes !== null) ? t.taxes : '-'),
                            'Net PnL (₹)': isEndOfData ? '-' : ((t.net_pnl !== undefined && t.net_pnl !== null) ? t.net_pnl : '-'),
                            'PnL (%)': isEndOfData ? '-' : ((t.pnl_pct !== undefined && t.pnl_pct !== null) ? t.pnl_pct : '-'),
                            'Duration': t.duration || 'Running',
                            'Weekday': t.weekday || ''
                        };
                    }),
                    format: 'excel'
                })
            });
            if (!res.ok) throw new Error('Excel export failed');
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${safeName}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            showToast(`Exported ${trades.length} trades to Excel`, 'success');
        } catch (err) {
            showToast(`Export error: ${err.message}`, 'error');
        }
    }
}

async function exportBacktestPdf() {
    if (!AppState.backtestResults) {
        showToast('No backtest results available to export as PDF', 'error');
        return;
    }

    const strategyName = (elements.btStrategyNameInput && elements.btStrategyNameInput.value.trim()) 
        || (AppState.backtestStrategies[AppState.currentBacktestStrategyIdx]?.name) 
        || 'Backtest_Report';

    const safeName = strategyName.replace(/[\\/*?:"<>|]/g, '_').trim();
    const brokerageVal = elements.btBrokerageInput ? Number(elements.btBrokerageInput.value) || 20 : 20;

    try {
        showToast('Generating PDF Backtest Report...', 'info');
        const payload = {
            strategy_name: strategyName,
            timeframe: AppState.backtestResults.timeframe || '1d',
            duration_seconds: AppState.backtestResults.duration_seconds || 0,
            capital_per_trade: elements.btCapitalInput ? Number(elements.btCapitalInput.value) || 100000 : 100000,
            slippage_pct: elements.btSlippageInput ? Number(elements.btSlippageInput.value) || 0.5 : 0.5,
            brokerage_per_order: brokerageVal,
            overall_report: AppState.backtestResults.overall_report || {},
            year_wise_returns: AppState.backtestResults.year_wise_returns || [],
            drawdown_chart: AppState.backtestResults.drawdown_chart || { dates: [], drawdowns: [] },
            diagnostics: (AppState.diagnosticsActive && AppState.backtestResults.diagnostics) ? AppState.backtestResults.diagnostics : {},
            summary: AppState.backtestResults.summary || {}
        };

        const res = await fetch('/api/export-backtest-pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.message || `PDF export failed (HTTP ${res.status})`);
        }

        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${safeName}_Backtest_Report.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        showToast(`Downloaded PDF report for "${strategyName}"`, 'success');
    } catch (err) {
        showToast(`PDF Export error: ${err.message}`, 'error');
    }
}

// Technical Chart View Across Timeframes (Fallback / Safe Guard)
async function loadChartForSymbol(symbol, timeframe = null) {
    if (!symbol || !elements.chartSymbolInput || !document.getElementById('plotly-chart-container')) return;
    symbol = symbol.trim().toUpperCase();
    AppState.currentChartSymbol = symbol;
    elements.chartSymbolInput.value = symbol;
    
    if (timeframe) {
        AppState.chartTimeframe = timeframe;
    }
    
    // Update active timeframe button in chart
    elements.chartTimeframeButtons.forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-tf') === AppState.chartTimeframe);
    });
    
    try {
        const res = await fetch(`/api/chart-data?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(AppState.chartTimeframe)}`);
        const data = await res.json();
        
        if (data.status !== 'ok') {
            showToast(data.message || `No data found for ${symbol}`, 'error');
            return;
        }
        
        // Update quote stats
        const latest = data.latest;
        elements.quotePrice.textContent = `₹${latest.close.toFixed(2)}`;
        
        if (latest.pct_change > 0) {
            elements.quoteChange.innerHTML = `<span style="color: var(--accent-green)">+${latest.pct_change}%</span>`;
        } else if (latest.pct_change < 0) {
            elements.quoteChange.innerHTML = `<span style="color: var(--accent-red)">${latest.pct_change}%</span>`;
        } else {
            elements.quoteChange.textContent = `${latest.pct_change}%`;
        }
        
        elements.quoteVolume.textContent = formatNumber(latest.volume);
        elements.quoteRange.textContent = `₹${latest.low_period.toFixed(2)} - ₹${latest.high_period.toFixed(2)}`;
        
        // Split alert
        if (data.splits && Object.keys(data.splits).length > 0) {
            elements.chartSplitAlert.style.display = 'flex';
            const splitsStr = Object.entries(data.splits).map(([dt, ratio]) => `${dt} (Ratio: ${ratio})`).join(', ');
            elements.chartSplitDetails.textContent = splitsStr;
        } else {
            elements.chartSplitAlert.style.display = 'none';
        }
        
        // Plotly Candlestick + Volume chart
        renderPlotlyChart(data);
        
        // Render raw table
        renderRawDataTable(data);
        
    } catch (err) {
        console.error('Error loading chart data:', err);
        showToast(`Chart error: ${err.message}`, 'error');
    }
}

function renderPlotlyChart(data) {
    if (!window.Plotly) return;
    
    const volumeColors = [];
    for (let i = 0; i < data.close.length; i++) {
        const c = data.close[i];
        const pc = data.prev_close[i] || c;
        volumeColors.push(c >= pc ? '#10b981' : '#ef4444');
    }
    
    const candlestickTrace = {
        x: data.dates,
        open: data.open,
        high: data.high,
        low: data.low,
        close: data.close,
        type: 'candlestick',
        name: 'Price',
        increasing: { line: { color: '#10b981' } },
        decreasing: { line: { color: '#ef4444' } },
        xaxis: 'x',
        yaxis: 'y'
    };
    
    const volumeTrace = {
        x: data.dates,
        y: data.volume,
        type: 'bar',
        name: 'Volume',
        marker: { color: volumeColors },
        opacity: 0.75,
        xaxis: 'x',
        yaxis: 'y2'
    };
    
    const isIntraday = data.timeframe !== '1d' && data.timeframe !== 'daily';
    
    const layout = {
        dragmode: 'zoom',
        showlegend: false,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(5, 6, 15, 0.4)',
        margin: { t: 20, b: 30, l: 50, r: 20 },
        xaxis: {
            rangeslider: { visible: false },
            type: 'category',
            gridcolor: 'rgba(255, 255, 255, 0.05)',
            tickfont: { color: '#9ca3af', family: 'Plus Jakarta Sans', size: 10 },
            nticks: isIntraday ? 12 : 10
        },
        yaxis: {
            domain: [0.28, 1],
            title: { text: 'Price (₹)', font: { color: '#9ca3af' } },
            gridcolor: 'rgba(255, 255, 255, 0.05)',
            tickfont: { color: '#9ca3af', family: 'Plus Jakarta Sans' }
        },
        yaxis2: {
            domain: [0, 0.22],
            title: { text: 'Volume', font: { color: '#9ca3af' } },
            gridcolor: 'rgba(255, 255, 255, 0.05)',
            tickfont: { color: '#9ca3af', family: 'Plus Jakarta Sans' }
        },
        hovermode: 'x unified',
        font: { family: 'Plus Jakarta Sans', color: '#f3f4f6' }
    };
    
    Plotly.newPlot(elements.plotlyContainer, [candlestickTrace, volumeTrace], layout, {
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d']
    });
}

function renderRawDataTable(data) {
    elements.rawTableBody.innerHTML = '';
    const len = data.dates.length;
    const limit = Math.min(len, 60);
    
    for (let i = len - 1; i >= len - limit; i--) {
        const tr = document.createElement('tr');
        const c = data.close[i];
        const pc = data.prev_close[i] || c;
        const change = pc > 0 ? ((c - pc) / pc * 100).toFixed(2) : '0.00';
        const isUp = c >= pc;
        
        tr.innerHTML = `
            <td style="font-family: var(--font-mono); color: var(--text-muted);">${data.dates[i]}</td>
            <td style="font-family: var(--font-mono);">₹${data.open[i].toFixed(2)}</td>
            <td style="font-family: var(--font-mono);">₹${data.high[i].toFixed(2)}</td>
            <td style="font-family: var(--font-mono);">₹${data.low[i].toFixed(2)}</td>
            <td style="font-family: var(--font-mono); font-weight: 600;">₹${c.toFixed(2)}</td>
            <td><span class="${isUp ? 'badge-green' : 'badge-red'}">${isUp ? '+' : ''}${change}%</span></td>
            <td style="font-family: var(--font-mono); color: var(--text-muted);">${formatNumber(data.volume[i])}</td>
        `;
        elements.rawTableBody.appendChild(tr);
    }
}

// Global function to jump directly to chart / fundamentals
window.openChartForSymbol = function(symbol, timeframe = null) {
    openFundamentalsModal(symbol);
};

// Global function to copy stock symbol to clipboard
window.copyStockSymbol = function(symbol) {
    if (!symbol) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(symbol).then(() => {
            showToast(`Copied ${symbol} to clipboard`, 'success');
        }).catch(() => {
            showToast(`Symbol: ${symbol}`, 'info');
        });
    } else {
        showToast(`Symbol: ${symbol}`, 'info');
    }
};

// --- Stock Symbol Autosuggest for Technical Charts ---

async function loadAllSymbols() {
    if (AppState.allSymbols && AppState.allSymbols.length > 0) {
        return AppState.allSymbols;
    }
    try {
        const res = await fetch('/api/symbols?segment=all');
        const data = await res.json();
        AppState.allSymbols = data.symbols || [];
        return AppState.allSymbols;
    } catch (err) {
        console.error('Error fetching symbols for autosuggest:', err);
        return [];
    }
}

function initAutosuggest() {
    const input = elements.chartSymbolInput;
    const dropdown = elements.symbolSuggestionsDropdown;
    if (!input || !dropdown) return;

    let activeIndex = -1;
    let currentMatches = [];

    function closeDropdown() {
        dropdown.classList.remove('show');
        dropdown.innerHTML = '';
        activeIndex = -1;
        currentMatches = [];
    }

    function escapeHtml(str) {
        return str.replace(/[&<>"']/g, m => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[m]);
    }

    function highlightMatch(symbol, query) {
        const idx = symbol.indexOf(query);
        if (idx === -1) return escapeHtml(symbol);
        const before = escapeHtml(symbol.substring(0, idx));
        const match = escapeHtml(symbol.substring(idx, idx + query.length));
        const after = escapeHtml(symbol.substring(idx + query.length));
        return `${before}<span class="suggestion-match">${match}</span>${after}`;
    }

    function selectSymbol(sym) {
        input.value = sym;
        closeDropdown();
        loadChartForSymbol(sym);
    }

    function updateActiveItem() {
        const items = dropdown.querySelectorAll('.symbol-suggestion-item');
        items.forEach((item, idx) => {
            if (idx === activeIndex) {
                item.classList.add('active');
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('active');
            }
        });
    }

    function renderSuggestions(matches, query) {
        currentMatches = matches;
        activeIndex = -1;
        dropdown.innerHTML = '';

        if (matches.length === 0) {
            dropdown.innerHTML = `<div class="no-suggestions">No ticker found for "${escapeHtml(query)}"</div>`;
            dropdown.classList.add('show');
            return;
        }

        matches.forEach((sym, idx) => {
            const item = document.createElement('div');
            item.className = 'symbol-suggestion-item';
            item.dataset.symbol = sym;
            item.dataset.index = idx;
            item.innerHTML = `
                <span class="suggestion-ticker">${highlightMatch(sym, query)}</span>
                <span class="suggestion-badge">NSE EQ</span>
            `;

            item.addEventListener('mousedown', (e) => {
                e.preventDefault(); // Prevent input blur before click registers
                selectSymbol(sym);
            });

            item.addEventListener('mouseenter', () => {
                activeIndex = idx;
                updateActiveItem();
            });

            dropdown.appendChild(item);
        });

        dropdown.classList.add('show');
    }

    async function handleInput() {
        const query = input.value.trim().toUpperCase();
        if (!query) {
            closeDropdown();
            return;
        }

        await loadAllSymbols();

        const startsWith = [];
        const contains = [];

        for (const sym of AppState.allSymbols) {
            if (sym === query) {
                startsWith.unshift(sym);
            } else if (sym.startsWith(query)) {
                startsWith.push(sym);
            } else if (sym.includes(query)) {
                contains.push(sym);
            }
        }

        const matches = [...startsWith, ...contains].slice(0, 14);
        renderSuggestions(matches, query);
    }

    // Input typing & focus listeners
    input.addEventListener('input', handleInput);
    input.addEventListener('focus', () => {
        if (input.value.trim().length > 0) {
            handleInput();
        }
    });

    // Keyboard navigation (ArrowUp, ArrowDown, Enter, Escape)
    input.addEventListener('keydown', (e) => {
        const isOpen = dropdown.classList.contains('show');

        if (e.key === 'ArrowDown') {
            if (isOpen && currentMatches.length > 0) {
                e.preventDefault();
                activeIndex = (activeIndex + 1) % currentMatches.length;
                updateActiveItem();
            } else if (!isOpen && input.value.trim().length > 0) {
                handleInput();
            }
        } else if (e.key === 'ArrowUp') {
            if (isOpen && currentMatches.length > 0) {
                e.preventDefault();
                activeIndex = (activeIndex - 1 + currentMatches.length) % currentMatches.length;
                updateActiveItem();
            }
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (isOpen && activeIndex >= 0 && activeIndex < currentMatches.length) {
                selectSymbol(currentMatches[activeIndex]);
            } else if (input.value.trim()) {
                selectSymbol(input.value.trim().toUpperCase());
            }
        } else if (e.key === 'Escape') {
            closeDropdown();
        }
    });

    // Click outside dropdown to close
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            closeDropdown();
        }
    });
}

// Zerodha Parquet & Data Manager actions
async function refreshCorporateSplits() {
    elements.btnRefreshSplits.disabled = true;
    elements.btnRefreshSplits.textContent = 'Syncing...';
    try {
        const res = await fetch('/api/zerodha/sync-splits', { method: 'POST' });
        const data = await res.json();
        showToast(data.message, 'success');
        await loadZerodhaStatus();
    } catch (err) {
        showToast(`Splits sync error: ${err.message}`, 'error');
    } finally {
        elements.btnRefreshSplits.disabled = false;
        elements.btnRefreshSplits.textContent = '🔄 Sync / Refresh Corporate Actions';
    }
}

async function verifyZerodhaParquet() {
    elements.btnVerifyParquet.disabled = true;
    try {
        const res = await fetch('/api/zerodha/status');
        const data = await res.json();
        if (data.exists) {
            showToast(`✓ Parquet storage verified! Found ${data.total_tickers} stock files.`, 'success');
            await loadZerodhaStatus();
        } else {
            showToast(`Directory not found: ${data.directory}`, 'error');
        }
    } catch (err) {
        showToast(`Verification error: ${err.message}`, 'error');
    } finally {
        elements.btnVerifyParquet.disabled = false;
    }
}

async function syncDateRange() {
    const startDate = elements.rangeSyncStart.value;
    const endDate = elements.rangeSyncEnd.value;
    
    if (!startDate || !endDate) {
        showToast('Please select both start and end dates', 'error');
        return;
    }
    
    if (startDate > endDate) {
        showToast('Start date cannot be after end date', 'error');
        return;
    }
    
    elements.btnSyncRange.disabled = true;
    elements.btnSyncRange.textContent = 'Syncing Date Range...';
    
    try {
        const res = await fetch('/api/sync-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'range', start_date: startDate, end_date: endDate })
        });
        const data = await res.json();
        
        if (data.status === 'ok') {
            showToast(data.message, 'success');
            await loadStatus();
            await loadDates();
            // Automatically update the chart in Technical Charts tab
            if (AppState.currentChartSymbol) {
                await loadChartForSymbol(AppState.currentChartSymbol, AppState.chartTimeframe);
                showToast(`Technical Chart updated for ${AppState.currentChartSymbol}`, 'info');
            }
        } else if (data.status === 'info') {
            showToast(data.message, 'info');
            // Refresh the chart even if already up to date
            if (AppState.currentChartSymbol) {
                await loadChartForSymbol(AppState.currentChartSymbol, AppState.chartTimeframe);
            }
        } else {
            showToast(data.message, 'error');
        }
    } catch (err) {
        showToast(`Range sync error: ${err.message}`, 'error');
    } finally {
        elements.btnSyncRange.disabled = false;
        elements.btnSyncRange.textContent = 'Sync Missing Dates in Range';
    }
}

// Watchlist File Upload Handler
function initWatchlistUpload() {
    if (elements.segmentSelect) {
        elements.segmentSelect.addEventListener('change', (e) => {
            if (elements.watchlistUploadGroup) {
                elements.watchlistUploadGroup.style.display = (e.target.value === 'watchlist') ? 'block' : 'none';
            }
        });
    }
    
    const btSegmentSelect = document.getElementById('bt-segment-select');
    const btWatchlistUploadGroup = document.getElementById('bt-watchlist-upload-group');
    if (btSegmentSelect && btWatchlistUploadGroup) {
        btSegmentSelect.addEventListener('change', (e) => {
            btWatchlistUploadGroup.style.display = (e.target.value === 'watchlist') ? 'block' : 'none';
        });
    }
    
    const setupFileInput = (inputEl, infoEl) => {
        if (!inputEl) return;
        inputEl.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                const res = await fetch('/api/upload-watchlist', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    AppState.watchlistSymbols = data.symbols;
                    if (infoEl) {
                        infoEl.textContent = `✓ Parsed ${data.count} tickers from ${file.name}`;
                        infoEl.style.display = 'block';
                    }
                    showToast(`Loaded ${data.count} tickers from watchlist`, 'success');
                } else {
                    showToast(data.message, 'error');
                }
            } catch (err) {
                showToast(`Watchlist upload failed: ${err.message}`, 'error');
            }
        });
    };
    
    setupFileInput(elements.watchlistFileInput, elements.watchlistInfo);
    setupFileInput(document.getElementById('bt-watchlist-file-input'), document.getElementById('bt-watchlist-info'));
}

// Event Listeners
function initEventListeners() {
    // Session date select
    if (elements.sessionDateSelect) {
        elements.sessionDateSelect.addEventListener('change', (e) => {
            AppState.currentDate = e.target.value;
            loadSessionSummary(AppState.currentDate);
        });
    }
    
    // Screener strategy select
    if (elements.strategySelect) {
        elements.strategySelect.addEventListener('change', (e) => {
            selectStrategy(Number(e.target.value), 'screener');
        });
    }
    
    // Screener controls
    if (elements.btnRunScreener) elements.btnRunScreener.addEventListener('click', () => runScreener(false));
    if (elements.btnSaveStrategy) elements.btnSaveStrategy.addEventListener('click', () => saveCurrentStrategy(false));
    if (elements.btnDeleteStrategy) elements.btnDeleteStrategy.addEventListener('click', () => deleteCurrentStrategy(false));
    if (elements.btnExportExcel) elements.btnExportExcel.addEventListener('click', () => exportResults('excel'));
    if (elements.btnExportCsv) elements.btnExportCsv.addEventListener('click', () => exportResults('csv'));
    
    // Keyboard shortcut for screener: Ctrl + Enter
    if (elements.codeEditor) {
        elements.codeEditor.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                runScreener(false);
            }
        });
    }

    // Min Market Cap selector and input sync (Screener)
    if (elements.minMcapSelect && elements.minMcapInput) {
        elements.minMcapSelect.addEventListener('change', (e) => {
            if (e.target.value !== 'custom') {
                elements.minMcapInput.value = e.target.value;
            } else {
                elements.minMcapInput.focus();
                elements.minMcapInput.select();
            }
        });
        elements.minMcapInput.addEventListener('input', (e) => {
            const val = e.target.value;
            const matchingOpt = Array.from(elements.minMcapSelect.options).find(opt => opt.value === val);
            if (matchingOpt) {
                elements.minMcapSelect.value = val;
            } else {
                elements.minMcapSelect.value = 'custom';
            }
        });
    }

    // Min Market Cap selector and input sync (Backtest)
    if (elements.btMinMcapSelect && elements.btMinMcapInput) {
        elements.btMinMcapSelect.addEventListener('change', (e) => {
            if (e.target.value !== 'custom') {
                elements.btMinMcapInput.value = e.target.value;
            } else {
                elements.btMinMcapInput.focus();
                elements.btMinMcapInput.select();
            }
        });
        elements.btMinMcapInput.addEventListener('input', (e) => {
            const val = e.target.value;
            const matchingOpt = Array.from(elements.btMinMcapSelect.options).find(opt => opt.value === val);
            if (matchingOpt) {
                elements.btMinMcapSelect.value = val;
            } else {
                elements.btMinMcapSelect.value = 'custom';
            }
        });
    }

    // Backtest Analytics controls (Completely Decoupled)
    if (elements.btStrategySelect) {
        elements.btStrategySelect.addEventListener('change', (e) => {
            selectBacktestStrategy(Number(e.target.value));
        });
    }
    if (elements.btBtnRunBacktest) {
        elements.btBtnRunBacktest.addEventListener('click', runBacktest);
    }
    if (elements.btBtnSaveStrategy) {
        elements.btBtnSaveStrategy.addEventListener('click', saveCurrentBacktestStrategy);
    }
    if (elements.btBtnDeleteStrategy) {
        elements.btBtnDeleteStrategy.addEventListener('click', deleteCurrentBacktestStrategy);
    }
    if (elements.btBtnExportExcel) {
        elements.btBtnExportExcel.addEventListener('click', () => exportBacktestTrades('excel'));
    }
    if (elements.btBtnExportPdf) {
        elements.btBtnExportPdf.addEventListener('click', () => exportBacktestPdf());
    }
    if (elements.btBtnExportCsv) {
        elements.btBtnExportCsv.addEventListener('click', () => exportBacktestTrades('csv'));
    }
    if (elements.btCodeEditor) {
        elements.btCodeEditor.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                runBacktest();
            }
        });
    }

    // Backtest Results Controls (Image 1 Controls)
    if (elements.btBtnRecalculate) {
        elements.btBtnRecalculate.addEventListener('click', recalculateBacktest);
    }
    if (elements.btToggleBrokerage) {
        elements.btToggleBrokerage.addEventListener('change', recalculateBacktest);
    }
    if (elements.btBrokerageInput) {
        elements.btBrokerageInput.addEventListener('change', recalculateBacktest);
    }
    if (elements.btToggleTaxes) {
        elements.btToggleTaxes.addEventListener('change', recalculateBacktest);
    }
    if (elements.btSlippageInput) {
        elements.btSlippageInput.addEventListener('change', recalculateBacktest);
    }
    if (elements.btBtnResetDdChart) {
        elements.btBtnResetDdChart.addEventListener('click', () => {
            if (AppState.backtestResults && AppState.backtestResults.drawdown_chart) {
                renderDrawdownChart(AppState.backtestResults.drawdown_chart);
            }
        });
    }

    // Day of Week Filter Chips & Pills
    if (elements.btDayPills) {
        elements.btDayPills.forEach(pill => {
            pill.addEventListener('click', () => {
                const day = pill.getAttribute('data-day');
                if (pill.classList.contains('active')) {
                    pill.classList.remove('active');
                    AppState.backtestFilterDays.delete(day);
                } else {
                    pill.classList.add('active');
                    AppState.backtestFilterDays.add(day);
                }
                recalculateBacktest();
            });
        });
    }
    if (elements.btChipClear) {
        elements.btChipClear.addEventListener('click', () => {
            AppState.backtestFilterDays.clear();
            if (elements.btDayPills) {
                elements.btDayPills.forEach(p => p.classList.remove('active'));
            }
            recalculateBacktest();
        });
    }
    if (elements.btChipWeekdays) {
        elements.btChipWeekdays.addEventListener('click', () => {
            const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
            AppState.backtestFilterDays = new Set(weekdays);
            if (elements.btDayPills) {
                elements.btDayPills.forEach(p => {
                    const day = p.getAttribute('data-day');
                    if (weekdays.includes(day)) {
                        p.classList.add('active');
                    } else {
                        p.classList.remove('active');
                    }
                });
            }
            recalculateBacktest();
        });
    }
    
    // Year-wise Matrix Table Month Checkboxes (Instant Client-side Recalculation)
    document.querySelectorAll('.bt-month-cb').forEach(cb => {
        cb.addEventListener('change', () => {
            const m = cb.getAttribute('data-month');
            if (cb.checked) {
                AppState.backtestFilterMonths.add(m);
            } else {
                AppState.backtestFilterMonths.delete(m);
            }
            const header = cb.closest('.bt-month-header');
            if (header) {
                header.classList.toggle('excluded', !cb.checked);
            }
            updateYearWiseTableTotals();
        });
    });

    if (elements.btBtnSelectAllMonths) {
        elements.btBtnSelectAllMonths.addEventListener('click', () => {
            const allM = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            AppState.backtestFilterMonths = new Set(allM);
            document.querySelectorAll('.bt-month-cb').forEach(cb => {
                cb.checked = true;
                const header = cb.closest('.bt-month-header');
                if (header) header.classList.remove('excluded');
            });
            updateYearWiseTableTotals();
        });
    }

    if (elements.btBtnClearAllMonths) {
        elements.btBtnClearAllMonths.addEventListener('click', () => {
            AppState.backtestFilterMonths.clear();
            document.querySelectorAll('.bt-month-cb').forEach(cb => {
                cb.checked = false;
                const header = cb.closest('.bt-month-header');
                if (header) header.classList.add('excluded');
            });
            updateYearWiseTableTotals();
        });
    }
    
    // Chart controls
    if (elements.btnLoadChart) {
        elements.btnLoadChart.addEventListener('click', () => {
            const sym = elements.chartSymbolInput.value;
            loadChartForSymbol(sym);
        });
    }
    
    // Initialize stock autosuggest
    initAutosuggest();
    
    // Chart timeframe buttons
    elements.chartTimeframeButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tf = btn.getAttribute('data-tf');
            loadChartForSymbol(elements.chartSymbolInput.value, tf);
        });
    });
    
    // Data Manager controls
    if (elements.btnRefreshSplits) elements.btnRefreshSplits.addEventListener('click', refreshCorporateSplits);
    if (elements.btnVerifyParquet) elements.btnVerifyParquet.addEventListener('click', verifyZerodhaParquet);
    if (elements.btnSyncRange) elements.btnSyncRange.addEventListener('click', syncDateRange);
    if (elements.btnExportDb) {
        elements.btnExportDb.addEventListener('click', () => {
            window.location.href = '/api/export-database';
        });
    }

    // Initialize Backtest Ready Pop-out Modal
    initBacktestReadyModal();
}

/* ==========================================================================
   Backtest Ready Pop-out Notification System
   ========================================================================== */

function playReportReadyChime() {
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        const now = ctx.currentTime;
        
        const osc1 = ctx.createOscillator();
        const gain1 = ctx.createGain();
        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(587.33, now); // D5
        gain1.gain.setValueAtTime(0.08, now);
        gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
        osc1.connect(gain1);
        gain1.connect(ctx.destination);
        osc1.start(now);
        osc1.stop(now + 0.18);

        const osc2 = ctx.createOscillator();
        const gain2 = ctx.createGain();
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(880, now + 0.1); // A5
        gain2.gain.setValueAtTime(0.12, now + 0.1);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
        osc2.connect(gain2);
        gain2.connect(ctx.destination);
        osc2.start(now + 0.1);
        osc2.stop(now + 0.45);
    } catch (e) {
        // Audio playback gracefully ignored if user has not interacted with audio yet
    }
}

function showBacktestReadyModal(data) {
    if (!elements.btReportReadyModal) return;

    const trades = data.trades || [];
    const openTradesCount = trades.filter(isEndOfDataTrade).length;
    const closedTradesCount = trades.length - openTradesCount;
    const winsCount = data.winning_trades || 0;
    const lossesCount = data.losing_trades || 0;
    const netPnl = Number(data.net_pnl) || 0;
    const roiPct = Number(data.return_pct) || 0;
    const winRate = Number(data.win_rate_pct) || 0;
    const pf = (data.profit_factor !== null && data.profit_factor !== undefined) ? Number(data.profit_factor).toFixed(2) : '-';
    const maxDd = (data.max_drawdown_pct !== null && data.max_drawdown_pct !== undefined) ? `${Number(data.max_drawdown_pct).toFixed(2)}%` : '-';
    const tf = String(data.timeframe || '1d').toUpperCase();
    const seg = String(data.segment || 'nifty50').toUpperCase();
    const duration = data.duration_seconds ? `${data.duration_seconds}s` : 'Instant';

    if (elements.btReadySubtitle) {
        elements.btReadySubtitle.textContent = `Completed ${trades.length} simulation trades across ${seg} on ${tf === '1W' ? 'WEEKLY' : (tf === '1MO' ? 'MONTHLY' : tf)} timeframe.`;
    }

    if (elements.btReadyNetPnl) {
        elements.btReadyNetPnl.textContent = `${netPnl >= 0 ? '+' : ''}₹${formatNumber(netPnl)}`;
        elements.btReadyNetPnl.className = `bt-ready-kpi-val ${netPnl >= 0 ? 'positive' : 'negative'}`;
    }
    if (elements.btReadyRoi) {
        elements.btReadyRoi.textContent = `${roiPct >= 0 ? '+' : ''}${roiPct.toFixed(2)}% Net Return`;
    }
    if (elements.btReadyWinrate) {
        elements.btReadyWinrate.textContent = `${winRate.toFixed(1)}%`;
    }
    if (elements.btReadyWinLoss) {
        elements.btReadyWinLoss.textContent = `${winsCount} Wins / ${lossesCount} Losses`;
    }
    if (elements.btReadyTrades) {
        elements.btReadyTrades.textContent = `${trades.length}`;
    }
    if (elements.btReadyTradesStatus) {
        elements.btReadyTradesStatus.textContent = openTradesCount > 0 ? `${closedTradesCount} Closed | ${openTradesCount} Running` : `${closedTradesCount} Closed Trades`;
    }
    if (elements.btReadyPf) {
        elements.btReadyPf.textContent = pf;
    }
    if (elements.btReadyMaxdd) {
        elements.btReadyMaxdd.textContent = `Max DD: ${maxDd}`;
    }
    if (elements.btReadyTimeframe) {
        elements.btReadyTimeframe.textContent = tf === '1W' ? 'Weekly' : (tf === '1MO' ? 'Monthly' : (tf === '1D' ? 'Daily (EOD)' : tf));
    }
    if (elements.btReadySegment) {
        elements.btReadySegment.textContent = seg;
    }
    if (elements.btReadyDuration) {
        elements.btReadyDuration.textContent = duration;
    }
    if (elements.btReadyDaterange) {
        const s = elements.btScreenStartDate ? elements.btScreenStartDate.value : '';
        const e = elements.btScreenEndDate ? elements.btScreenEndDate.value : '';
        elements.btReadyDaterange.textContent = (s && e) ? `${s} to ${e}` : (e ? `Up to ${e}` : 'Full Available History');
    }

    elements.btReportReadyModal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    playReportReadyChime();
}

function closeBacktestReadyModal() {
    if (elements.btReportReadyModal) {
        elements.btReportReadyModal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

function initBacktestReadyModal() {
    if (elements.btnCloseBtReadyModal) {
        elements.btnCloseBtReadyModal.addEventListener('click', closeBacktestReadyModal);
    }
    if (elements.btnBtReadyDismiss) {
        elements.btnBtReadyDismiss.addEventListener('click', closeBacktestReadyModal);
    }
    if (elements.btnBtReadyView) {
        elements.btnBtReadyView.addEventListener('click', () => {
            closeBacktestReadyModal();
            if (elements.btTradeLogContainer) {
                elements.btTradeLogContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    }
    if (elements.btnBtReadyPrint) {
        elements.btnBtReadyPrint.addEventListener('click', () => {
            closeBacktestReadyModal();
            exportBacktestPdf();
        });
    }
    if (elements.btReportReadyModal) {
        elements.btReportReadyModal.addEventListener('click', (e) => {
            if (e.target === elements.btReportReadyModal) {
                closeBacktestReadyModal();
            }
        });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && elements.btReportReadyModal && elements.btReportReadyModal.style.display === 'flex') {
            closeBacktestReadyModal();
        }
    });
}

/**
 * Toast Notification Helper
 */
function showToast(message, type = 'info', duration = 3200) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast-message ${type === 'success' ? 'toast-success' : ''}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';
    
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('toast-fadeout');
        setTimeout(() => toast.remove(), 320);
    }, duration);
}

/**
 * GenAI Prompt & Python Template Modal Controller
 */
function initGenAITemplateModal() {
    if (!elements.genaiTemplateModal) return;

    // Open modal handler for both Screener and Backtest
    const openModal = (e) => {
        if (e) e.preventDefault();
        elements.genaiTemplateModal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    };

    if (elements.scLinkGenaiTemplate) {
        elements.scLinkGenaiTemplate.addEventListener('click', openModal);
    }
    if (elements.btLinkGenaiTemplate) {
        elements.btLinkGenaiTemplate.addEventListener('click', openModal);
    }
    document.querySelectorAll('.genai-guide-link').forEach(link => {
        link.addEventListener('click', openModal);
    });

    // Close modal function
    const closeModal = () => {
        elements.genaiTemplateModal.style.display = 'none';
        document.body.style.overflow = '';
    };

    if (elements.btnCloseGenaiModal) {
        elements.btnCloseGenaiModal.addEventListener('click', closeModal);
    }

    // Close on overlay backdrop click
    elements.genaiTemplateModal.addEventListener('click', (e) => {
        if (e.target === elements.genaiTemplateModal) {
            closeModal();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && elements.genaiTemplateModal && elements.genaiTemplateModal.style.display === 'flex') {
            closeModal();
        }
    });

    // Tab switching inside modal
    if (elements.genaiModalTabs) {
        elements.genaiModalTabs.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetTab = btn.getAttribute('data-tab');
                elements.genaiModalTabs.forEach(b => b.classList.remove('active'));
                
                const allPanes = elements.genaiTemplateModal.querySelectorAll('.modal-tab-pane');
                allPanes.forEach(pane => pane.classList.remove('active'));
                
                btn.classList.add('active');
                const targetPane = document.getElementById(targetTab);
                if (targetPane) targetPane.classList.add('active');
            });
        });
    }

    // Clipboard copy helper
    const copyToClipboard = (text, buttonElement, successMsg) => {
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(() => {
                onCopySuccess(buttonElement, successMsg);
            }).catch(() => {
                fallbackCopy(text, buttonElement, successMsg);
            });
        } else {
            fallbackCopy(text, buttonElement, successMsg);
        }
    };

    const fallbackCopy = (text, buttonElement, successMsg) => {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            onCopySuccess(buttonElement, successMsg);
        } catch (err) {
            showToast('Unable to copy automatically. Please select text to copy.', 'error');
        }
        document.body.removeChild(textarea);
    };

    const onCopySuccess = (btn, successMsg) => {
        const originalHtml = btn.innerHTML;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> <span>Copied!</span>`;
        btn.classList.add('btn-success');
        showToast(successMsg, 'success');
        setTimeout(() => {
            btn.innerHTML = originalHtml;
            btn.classList.remove('btn-success');
        }, 2400);
    };

    // Copy GenAI Prompt Button
    if (elements.btnCopyGenaiPrompt && elements.textGenaiPrompt) {
        elements.btnCopyGenaiPrompt.addEventListener('click', () => {
            const text = elements.textGenaiPrompt.textContent;
            copyToClipboard(text, elements.btnCopyGenaiPrompt, 'Master GenAI prompt copied to clipboard! Paste into ChatGPT or Claude.');
        });
    }

    // Copy Python Code Button
    if (elements.btnCopyPythonCode && elements.textPythonCode) {
        elements.btnCopyPythonCode.addEventListener('click', () => {
            const text = elements.textPythonCode.textContent;
            copyToClipboard(text, elements.btnCopyPythonCode, 'Python Strategy template copied to clipboard!');
        });
    }
}

// --- Fundamentals Modal & Manager System ---

let _activeFundStatementData = null;

async function openFundamentalsModal(symbol) {
    symbol = (symbol || '').toUpperCase().trim();
    if (!symbol) return;

    const modal = document.getElementById('fundamentals-modal');
    if (!modal) return;

    modal.style.display = 'flex';
    modal.style.opacity = '1';
    document.body.style.overflow = 'hidden';
    document.getElementById('fund-modal-symbol-badge').textContent = symbol;
    document.getElementById('fund-modal-company-name').textContent = `Loading ${symbol} fundamentals...`;
    document.getElementById('fund-modal-sector').textContent = 'Sector: ...';
    document.getElementById('fund-modal-industry').textContent = 'Industry: ...';
    document.getElementById('fund-modal-last-updated').textContent = 'Updated: ...';

    // Clear ratios
    ['fm-mcap', 'fm-pe', 'fm-forward-pe', 'fm-pb', 'fm-roe', 'fm-roa', 'fm-de', 'fm-op-margin', 'fm-div-yield', 'fm-eps'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '...';
    });

    // Clear tables
    ['qpnl', 'ypnl', 'ybs', 'ycf'].forEach(tab => {
        const thead = document.getElementById(`fund-thead-${tab}`);
        const tbody = document.getElementById(`fund-tbody-${tab}`);
        if (thead) thead.innerHTML = '';
        if (tbody) tbody.innerHTML = `<tr><td style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Loading ${tab.toUpperCase()} statement...</td></tr>`;
    });

    try {
        const res = await fetch(`/api/fundamentals/${symbol}?fetch_online=true`);
        if (!res.ok) {
            throw new Error(`Failed to load fundamentals for ${symbol}`);
        }
        const json = await res.json();
        if (json.status !== 'ok' || !json.data) {
            throw new Error(json.message || 'No data found');
        }

        const data = json.data;
        _activeFundStatementData = data;
        renderFundamentalsModal(data);
    } catch (err) {
        console.error('Error fetching fundamentals:', err);
        document.getElementById('fund-modal-company-name').textContent = `${symbol} (Failed to load)`;
        showToast(`Could not load fundamentals for ${symbol}: ${err.message}`, 'error');
        ['qpnl', 'ypnl', 'ybs', 'ycf'].forEach(tab => {
            const tbody = document.getElementById(`fund-tbody-${tab}`);
            if (tbody) tbody.innerHTML = `<tr><td style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No data available.</td></tr>`;
        });
    }
}
window.openFundamentalsModal = openFundamentalsModal;

function renderFundamentalsModal(data) {
    const ratios = data.ratios || {};
    document.getElementById('fund-modal-company-name').textContent = ratios.companyName || data.symbol;
    document.getElementById('fund-modal-sector').textContent = `Sector: ${ratios.sector || 'N/A'}`;
    document.getElementById('fund-modal-industry').textContent = `Industry: ${ratios.industry || 'N/A'}`;
    document.getElementById('fund-modal-last-updated').textContent = `Updated: ${ratios.lastUpdated || 'Recently'}`;

    // Populate Key Ratio cards
    const mcapStr = ratios.marketCapCr ? `₹${Number(ratios.marketCapCr).toLocaleString('en-IN')} Cr` : '-';
    const peStr = ratios.pe ? Number(ratios.pe).toFixed(2) : '-';
    const fPeStr = ratios.forwardPE ? Number(ratios.forwardPE).toFixed(2) : '-';
    const pbStr = ratios.pb ? Number(ratios.pb).toFixed(2) : '-';
    const roeStr = ratios.roe !== null && ratios.roe !== undefined ? `${Number(ratios.roe).toFixed(2)}%` : '-';
    const roaStr = ratios.roa !== null && ratios.roa !== undefined ? `${Number(ratios.roa).toFixed(2)}%` : '-';
    const deStr = ratios.debtToEquity !== null && ratios.debtToEquity !== undefined ? Number(ratios.debtToEquity).toFixed(2) : '-';
    const opmStr = ratios.operatingMargin !== null && ratios.operatingMargin !== undefined ? `${Number(ratios.operatingMargin).toFixed(2)}%` : '-';
    const divStr = ratios.dividendYield !== null && ratios.dividendYield !== undefined ? `${Number(ratios.dividendYield).toFixed(2)}%` : '-';
    const epsStr = ratios.trailingEps ? `₹${Number(ratios.trailingEps).toFixed(2)}` : '-';

    document.getElementById('fm-mcap').textContent = mcapStr;
    document.getElementById('fm-pe').textContent = peStr;
    document.getElementById('fm-forward-pe').textContent = fPeStr;
    document.getElementById('fm-pb').textContent = pbStr;
    document.getElementById('fm-roe').textContent = roeStr;
    document.getElementById('fm-roa').textContent = roaStr;
    document.getElementById('fm-de').textContent = deStr;
    document.getElementById('fm-op-margin').textContent = opmStr;
    document.getElementById('fm-div-yield').textContent = divStr;
    document.getElementById('fm-eps').textContent = epsStr;

    // Render statements
    renderStatementTable('qpnl', data.quarterly_pnl);
    renderStatementTable('ypnl', data.yearly_pnl);
    renderStatementTable('ybs', data.yearly_balance_sheet);
    renderStatementTable('ycf', data.yearly_cash_flow);
}

function renderStatementTable(tabKey, stmtObj) {
    const thead = document.getElementById(`fund-thead-${tabKey}`);
    const tbody = document.getElementById(`fund-tbody-${tabKey}`);
    if (!thead || !tbody) return;

    if (!stmtObj || !stmtObj.dates || stmtObj.dates.length === 0 || !stmtObj.metrics) {
        thead.innerHTML = `<tr><th>Line Item</th><th>No Data Available</th></tr>`;
        tbody.innerHTML = `<tr><td colspan="2" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No historical data available for this statement.</td></tr>`;
        return;
    }

    const dates = stmtObj.dates;
    const metrics = stmtObj.metrics;

    // Header
    let thHtml = `<tr><th style="min-width: 220px; position: sticky; left: 0; background: #0f172a; z-index: 2;">Financial Metric</th>`;
    dates.forEach(d => {
        thHtml += `<th style="text-align: right; min-width: 110px; font-family: var(--font-mono);">${formatDateDDMMMYYYY(d)}</th>`;
    });
    thHtml += `</tr>`;
    thead.innerHTML = thHtml;

    // Body rows
    let trHtml = '';
    const metricNames = Object.keys(metrics);

    metricNames.forEach((mName) => {
        const isHighlight = ['Operating Revenue', 'Total Revenue', 'Operating Income', 'EBITDA', 'Net Income', 'Basic EPS', 'Diluted EPS', 'Total Assets', 'Stockholders Equity', 'Total Debt', 'Working Capital', 'Operating Cash Flow', 'Free Cash Flow'].includes(mName);
        const rowStyle = isHighlight ? 'background: rgba(59, 130, 246, 0.08); font-weight: 600;' : '';
        const nameColor = isHighlight ? 'color: #93c5fd;' : 'color: #e2e8f0;';

        trHtml += `<tr style="${rowStyle}">`;
        trHtml += `<td style="position: sticky; left: 0; background: ${isHighlight ? '#141e33' : '#0a0f1d'}; ${nameColor} z-index: 1;">${mName}</td>`;

        dates.forEach(d => {
            const val = metrics[mName] ? metrics[mName][d] : null;
            let valDisplay = '-';
            let color = 'color: #94a3b8;';

            if (val !== null && val !== undefined) {
                const num = Number(val);
                if (!isNaN(num)) {
                    valDisplay = num.toLocaleString('en-IN', { maximumFractionDigits: 2 });
                    if (num > 0) color = isHighlight ? 'color: #34d399;' : 'color: #cbd5e1;';
                    else if (num < 0) color = 'color: #f87171;';
                } else {
                    valDisplay = val;
                }
            }
            trHtml += `<td style="text-align: right; font-family: var(--font-mono); ${color}">${valDisplay}</td>`;
        });
        trHtml += `</tr>`;
    });

    tbody.innerHTML = trHtml;
}

function initFundamentalsSystem() {
    // Modal Close button
    const closeBtn = document.getElementById('fund-modal-close-btn');
    const bottomCloseBtn = document.getElementById('fund-modal-bottom-close-btn');
    const modal = document.getElementById('fundamentals-modal');

    const closeModal = () => {
        if (modal) modal.style.display = 'none';
        document.body.style.overflow = '';
    };

    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (bottomCloseBtn) bottomCloseBtn.addEventListener('click', closeModal);
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    }

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal && modal.style.display === 'flex') {
            closeModal();
        }
    });

    // Modal tabs switching
    document.querySelectorAll('.fund-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-fund-tab');
            document.querySelectorAll('.fund-tab-btn').forEach(b => {
                b.classList.remove('active', 'btn-primary');
                b.classList.add('btn-secondary');
            });
            btn.classList.add('active', 'btn-primary');
            btn.classList.remove('btn-secondary');

            document.querySelectorAll('.fund-tab-content').forEach(pane => pane.style.display = 'none');
            const targetPane = document.getElementById(`fund-pane-${targetTab}`);
            if (targetPane) targetPane.style.display = 'block';
        });
    });

    // Sync buttons in Manager Tab
    const btnNifty50 = document.getElementById('btn-sync-fund-nifty50');
    const btnNifty500 = document.getElementById('btn-sync-fund-nifty500');
    const btnAll = document.getElementById('btn-sync-fund-all');
    const forceCheck = document.getElementById('fund-force-refresh');

    const triggerSync = async (segment) => {
        const force = forceCheck ? forceCheck.checked : false;
        try {
            showToast(`Initiating fundamentals sync for ${segment.toUpperCase()}...`, 'info');
            const res = await fetch('/api/fundamentals/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ segment, force })
            });
            const data = await res.json();
            if (res.status === 409) {
                showToast(data.message || 'Sync job already running', 'warning');
            } else if (data.status === 'ok') {
                showToast(data.message, 'success');
                startFundamentalsSyncPolling();
            } else {
                showToast(data.message || 'Sync failed', 'error');
            }
        } catch (err) {
            showToast(`Sync error: ${err.message}`, 'error');
        }
    };

    if (btnNifty50) btnNifty50.addEventListener('click', () => triggerSync('nifty50'));
    if (btnNifty500) btnNifty500.addEventListener('click', () => triggerSync('nifty500'));
    if (btnAll) btnAll.addEventListener('click', () => triggerSync('all'));

    // Load initial status
    loadFundamentalsStatus();
}

let _fundSyncPollInterval = null;

async function loadFundamentalsStatus() {
    try {
        const res = await fetch('/api/fundamentals/status');
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === 'ok') {
            const countEl = document.getElementById('fund-tracked-count');
            const syncEl = document.getElementById('fund-last-sync-time');
            if (countEl) countEl.textContent = `${data.total_tracked} Stocks`;
            if (syncEl) syncEl.textContent = data.last_sync || 'Never';

            if (data.sync_job && data.sync_job.is_running) {
                startFundamentalsSyncPolling();
            }
        }
    } catch (err) {
        console.warn('Error loading fundamentals status:', err);
    }
}

function startFundamentalsSyncPolling() {
    if (_fundSyncPollInterval) return;

    const progressWrap = document.getElementById('fund-sync-progress-wrap');
    const progressBar = document.getElementById('fund-sync-progress-bar');
    const statusText = document.getElementById('fund-sync-status-text');
    const percentText = document.getElementById('fund-sync-percent-text');
    if (progressWrap) progressWrap.style.display = 'block';

    _fundSyncPollInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/fundamentals/status');
            if (!res.ok) return;
            const data = await res.json();
            if (data.status === 'ok' && data.sync_job) {
                const job = data.sync_job;
                const pct = job.total > 0 ? Math.round((job.current / job.total) * 100) : 0;

                if (progressBar) progressBar.style.width = `${pct}%`;
                if (percentText) percentText.textContent = `${pct}% (${job.current}/${job.total})`;
                if (statusText) statusText.textContent = `Downloading fundamentals: ${job.current_symbol || 'fetching...'} (${pct}%)`;

                if (!job.is_running) {
                    clearInterval(_fundSyncPollInterval);
                    _fundSyncPollInterval = null;
                    if (progressWrap) setTimeout(() => { progressWrap.style.display = 'none'; }, 2500);
                    showToast(`Fundamentals sync completed! Total: ${data.total_tracked} stocks.`, 'success');
                    loadFundamentalsStatus();
                }
            }
        } catch (e) {
            console.warn('Sync poll error:', e);
        }
    }, 1500);
}

// --- Pre-Adjusted Daily Parquet Cache Management ---

function initDailyCacheSystem() {
    const btnNifty50 = document.getElementById('btn-build-cache-nifty50');
    const btnNifty500 = document.getElementById('btn-build-cache-nifty500');
    const btnAll = document.getElementById('btn-build-cache-all');
    const forceCheck = document.getElementById('daily-cache-force-refresh');

    const triggerBuild = async (segment) => {
        const force = forceCheck ? forceCheck.checked : false;
        try {
            showToast(`Initiating Daily Cache build for ${segment.toUpperCase()}...`, 'info');
            const res = await fetch('/api/daily-cache/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ segment, force })
            });
            const data = await res.json();
            if (res.status === 409) {
                showToast(data.message || 'Build job already running', 'warning');
            } else if (data.status === 'ok') {
                showToast(data.message, 'success');
                startDailyCachePolling();
            } else {
                showToast(data.message || 'Build failed', 'error');
            }
        } catch (err) {
            showToast(`Build error: ${err.message}`, 'error');
        }
    };

    if (btnNifty50) btnNifty50.addEventListener('click', () => triggerBuild('nifty50'));
    if (btnNifty500) btnNifty500.addEventListener('click', () => triggerBuild('nifty500'));
    if (btnAll) btnAll.addEventListener('click', () => triggerBuild('all'));

    loadDailyCacheStatus();
}

let _dailyCachePollInterval = null;

async function loadDailyCacheStatus() {
    try {
        const res = await fetch('/api/daily-cache/status');
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === 'ok') {
            const cache = data.cache || {};
            const countEl = document.getElementById('daily-cache-count');
            const syncEl = document.getElementById('daily-cache-last-time');
            if (countEl) countEl.textContent = `${cache.total_cached || 0} / ${cache.total_available || 0} Stocks`;
            if (syncEl) syncEl.textContent = cache.last_updated || 'Never';

            if (data.sync_job && data.sync_job.is_running) {
                startDailyCachePolling();
            }
        }
    } catch (err) {
        console.warn('Error loading daily cache status:', err);
    }
}

function startDailyCachePolling() {
    if (_dailyCachePollInterval) return;

    const progressWrap = document.getElementById('daily-cache-progress-wrap');
    const progressBar = document.getElementById('daily-cache-progress-bar');
    const statusText = document.getElementById('daily-cache-status-text');
    const percentText = document.getElementById('daily-cache-percent-text');
    if (progressWrap) progressWrap.style.display = 'block';

    _dailyCachePollInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/daily-cache/status');
            if (!res.ok) return;
            const data = await res.json();
            const job = data.sync_job;
            const cache = data.cache || {};

            const countEl = document.getElementById('daily-cache-count');
            const syncEl = document.getElementById('daily-cache-last-time');
            if (countEl) countEl.textContent = `${cache.total_cached || 0} / ${cache.total_available || 0} Stocks`;
            if (syncEl) syncEl.textContent = cache.last_updated || 'Never';

            if (job) {
                const pct = Math.min(100, Math.max(0, job.progress || 0));
                if (progressBar) progressBar.style.width = `${pct}%`;
                if (percentText) percentText.textContent = `${pct}%`;
                if (statusText) statusText.textContent = job.message || `Processing ${job.symbol || ''}...`;

                if (!job.is_running) {
                    clearInterval(_dailyCachePollInterval);
                    _dailyCachePollInterval = null;
                    if (progressWrap) {
                        setTimeout(() => { progressWrap.style.display = 'none'; }, 2500);
                    }
                    if (job.status === 'complete') {
                        showToast(job.message || 'Daily cache build complete!', 'success');
                    } else if (job.status === 'error') {
                        showToast(job.message || 'Daily cache build failed.', 'error');
                    }
                }
            }
        } catch (err) {
            console.error('Error polling daily cache status:', err);
        }
    }, 1200);
}

// ---------------------------------------------------------------------
// Institutional Quantitative Diagnostics & Robustness Suite
// ---------------------------------------------------------------------
let _currentDiagnostics = null;

function formatRupeeVal(val) {
    if (val === undefined || val === null || isNaN(val)) return '₹ 0.00';
    const num = Number(val);
    const sign = num < 0 ? '-₹ ' : '₹ ';
    return `${sign}${Math.abs(num).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const PLOTLY_DARK_LAYOUT = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {
        family: 'Outfit, Plus Jakarta Sans, sans-serif',
        color: '#94a3b8',
        size: 11
    },
    margin: { l: 55, r: 25, t: 25, b: 40 },
    xaxis: {
        gridcolor: 'rgba(255, 255, 255, 0.05)',
        zerolinecolor: 'rgba(255, 255, 255, 0.1)',
        tickfont: { color: '#94a3b8', size: 10 }
    },
    yaxis: {
        gridcolor: 'rgba(255, 255, 255, 0.05)',
        zerolinecolor: 'rgba(255, 255, 255, 0.1)',
        tickfont: { color: '#94a3b8', size: 10 }
    },
    legend: {
        font: { color: '#cbd5e1', size: 10 },
        bgcolor: 'rgba(15, 23, 42, 0.75)',
        bordercolor: 'rgba(255, 255, 255, 0.1)',
        borderwidth: 1
    }
};

const PLOTLY_CONFIG = {
    responsive: true,
    displayModeBar: false
};

function triggerSubviewRender(svId) {
    if (!_currentDiagnostics) return;
    if (svId === 'view-benchmark' && _currentDiagnostics.benchmark_comparison) {
        renderBenchmarkComparison(_currentDiagnostics.benchmark_comparison);
    } else if (svId === 'view-oos' && _currentDiagnostics.out_of_sample_split) {
        renderOosSplit(_currentDiagnostics.out_of_sample_split);
    } else if (svId === 'view-heatmap' && _currentDiagnostics.parameter_sensitivity) {
        renderParameterHeatmap(_currentDiagnostics.parameter_sensitivity);
    } else if (svId === 'view-montecarlo' && _currentDiagnostics.monte_carlo) {
        renderMonteCarlo(_currentDiagnostics.monte_carlo);
    } else if (svId === 'view-regime' && _currentDiagnostics.regime_split) {
        renderRegimeSplit(_currentDiagnostics.regime_split);
    } else if (svId === 'view-pnldist' && _currentDiagnostics.pnl_distribution) {
        renderPnlDistribution(_currentDiagnostics.pnl_distribution);
    } else if (svId === 'view-sectormcap' && _currentDiagnostics.sector_mcap) {
        renderSectorMcap(_currentDiagnostics.sector_mcap);
    } else if (svId === 'view-timeline' && _currentDiagnostics.concurrent_timeline) {
        renderConcurrentTimeline(_currentDiagnostics.concurrent_timeline);
    } else if (svId === 'view-rolling' && _currentDiagnostics.rolling_metrics) {
        renderRollingMetrics(_currentDiagnostics.rolling_metrics);
    } else if (svId === 'view-sizing' && _currentDiagnostics.position_sizing) {
        renderPositionSizingComparison(_currentDiagnostics.position_sizing);
    }
}

function resetDiagnosticsUI() {
    AppState.diagnosticsActive = false;
    _currentDiagnostics = null;
    if (AppState.backtestResults) {
        AppState.backtestResults.diagnostics = null;
    }
    if (elements.diagStandbyPlaceholder) elements.diagStandbyPlaceholder.style.display = 'flex';
    if (elements.diagContentWrapper) elements.diagContentWrapper.style.display = 'none';
    if (elements.diagMasterTabsWrap) elements.diagMasterTabsWrap.style.display = 'none';
    
    if (elements.btnToggleDiagnostics) {
        elements.btnToggleDiagnostics.classList.remove('btn-active-diag');
        elements.btnToggleDiagnostics.disabled = false;
    }
    if (elements.btnToggleDiagnosticsIcon) elements.btnToggleDiagnosticsIcon.textContent = '⚡';
    if (elements.btnToggleDiagnosticsText) elements.btnToggleDiagnosticsText.textContent = 'Calculate Diagnostics';
    if (elements.btnRunDiagnosticsHero) {
        elements.btnRunDiagnosticsHero.disabled = false;
        elements.btnRunDiagnosticsHero.innerHTML = '<span>⚡ Calculate &amp; Populate Diagnostics</span>';
    }
}

async function toggleOrCalculateDiagnostics() {
    if (!AppState.backtestResults || !AppState.backtestResults.trades || AppState.backtestResults.trades.length === 0) {
        showToast('Please run a backtest first before computing quantitative diagnostics', 'warning');
        return;
    }

    // If diagnostics already computed in memory:
    const hasCachedData = AppState.backtestResults.diagnostics && Object.keys(AppState.backtestResults.diagnostics).length > 0;
    
    if (hasCachedData) {
        AppState.diagnosticsActive = !AppState.diagnosticsActive;
        if (AppState.diagnosticsActive) {
            if (elements.diagStandbyPlaceholder) elements.diagStandbyPlaceholder.style.display = 'none';
            if (elements.diagContentWrapper) elements.diagContentWrapper.style.display = 'block';
            if (elements.diagMasterTabsWrap) elements.diagMasterTabsWrap.style.display = 'flex';
            if (elements.btnToggleDiagnostics) elements.btnToggleDiagnostics.classList.add('btn-active-diag');
            if (elements.btnToggleDiagnosticsIcon) elements.btnToggleDiagnosticsIcon.textContent = '✅';
            if (elements.btnToggleDiagnosticsText) elements.btnToggleDiagnosticsText.textContent = 'Diagnostics Active (Toggle)';
            
            const activeMaster = document.querySelector('.diag-master-pill.active');
            const targetId = activeMaster ? activeMaster.getAttribute('data-panel') : 'panel-robustness';
            const panel = document.getElementById(targetId);
            if (panel) {
                const activeSub = panel.querySelector('.diag-subpill.active');
                if (activeSub) {
                    triggerSubviewRender(activeSub.getAttribute('data-subview'));
                }
            }
            setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
            showToast('Quantitative diagnostics visible & included in PDF report', 'info');
        } else {
            if (elements.diagStandbyPlaceholder) elements.diagStandbyPlaceholder.style.display = 'flex';
            if (elements.diagContentWrapper) elements.diagContentWrapper.style.display = 'none';
            if (elements.diagMasterTabsWrap) elements.diagMasterTabsWrap.style.display = 'none';
            if (elements.btnToggleDiagnostics) elements.btnToggleDiagnostics.classList.remove('btn-active-diag');
            if (elements.btnToggleDiagnosticsIcon) elements.btnToggleDiagnosticsIcon.textContent = '⚡';
            if (elements.btnToggleDiagnosticsText) elements.btnToggleDiagnosticsText.textContent = 'Show Diagnostics';
            showToast('Quantitative diagnostics hidden & excluded from PDF report', 'info');
        }
        return;
    }

    // Not yet calculated: call backend to compute diagnostics on demand
    const rawTrades = AppState.rawBacktestTrades || AppState.backtestResults.trades || [];
    const capital = elements.btCapitalInput ? Number(elements.btCapitalInput.value) || 100000 : 100000;
    const slippage = elements.btSlippageInput ? Number(elements.btSlippageInput.value) || 0.5 : 0.5;
    const incBrokerage = elements.btToggleBrokerage ? elements.btToggleBrokerage.checked : true;
    const incTaxes = elements.btToggleTaxes ? elements.btToggleTaxes.checked : true;
    const brokerageVal = elements.btBrokerageInput ? Number(elements.btBrokerageInput.value) || 20 : 20;

    if (elements.btnToggleDiagnostics) elements.btnToggleDiagnostics.disabled = true;
    if (elements.btnRunDiagnosticsHero) elements.btnRunDiagnosticsHero.disabled = true;
    if (elements.btnToggleDiagnosticsIcon) elements.btnToggleDiagnosticsIcon.textContent = '⏳';
    if (elements.btnToggleDiagnosticsText) elements.btnToggleDiagnosticsText.textContent = 'Calculating...';
    if (elements.btnRunDiagnosticsHero) elements.btnRunDiagnosticsHero.innerHTML = '<span>⏳ Computing Monte Carlo &amp; Robustness (1,000x)...</span>';

    showToast('Calculating Institutional Quantitative Diagnostics & Robustness...', 'info');

    try {
        const res = await fetch('/api/backtest/diagnostics', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                trades: rawTrades,
                capital_per_trade: capital,
                slippage_pct: slippage,
                include_brokerage: incBrokerage,
                include_taxes: incTaxes,
                brokerage_per_order: brokerageVal
            })
        });

        const data = await res.json();
        if (data.status === 'success') {
            AppState.backtestResults.diagnostics = data.diagnostics || {};
            AppState.diagnosticsActive = true;

            if (data.overall_report) {
                AppState.backtestResults.overall_report = {
                    ...AppState.backtestResults.overall_report,
                    ...data.overall_report
                };
                renderOverallReport(AppState.backtestResults.overall_report);
            }

            if (elements.diagStandbyPlaceholder) elements.diagStandbyPlaceholder.style.display = 'none';
            if (elements.diagContentWrapper) elements.diagContentWrapper.style.display = 'block';
            if (elements.diagMasterTabsWrap) elements.diagMasterTabsWrap.style.display = 'flex';
            if (elements.btnToggleDiagnostics) elements.btnToggleDiagnostics.classList.add('btn-active-diag');
            if (elements.btnToggleDiagnosticsIcon) elements.btnToggleDiagnosticsIcon.textContent = '✅';
            if (elements.btnToggleDiagnosticsText) elements.btnToggleDiagnosticsText.textContent = 'Diagnostics Active (Toggle)';

            renderDiagnosticsSuite(data.diagnostics);

            const activeMaster = document.querySelector('.diag-master-pill.active');
            const targetId = activeMaster ? activeMaster.getAttribute('data-panel') : 'panel-robustness';
            const panel = document.getElementById(targetId);
            if (panel) {
                const activeSub = panel.querySelector('.diag-subpill.active');
                if (activeSub) {
                    triggerSubviewRender(activeSub.getAttribute('data-subview'));
                }
            }
            setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
            showToast('Institutional diagnostics & robustness suite calculated successfully!', 'success');
        } else {
            showToast(`Failed to calculate diagnostics: ${data.message || 'Unknown error'}`, 'error');
        }
    } catch (err) {
        showToast(`Diagnostics error: ${err.message}`, 'error');
    } finally {
        if (elements.btnToggleDiagnostics) elements.btnToggleDiagnostics.disabled = false;
        if (elements.btnRunDiagnosticsHero) {
            elements.btnRunDiagnosticsHero.disabled = false;
            elements.btnRunDiagnosticsHero.innerHTML = '<span>⚡ Calculate &amp; Populate Diagnostics</span>';
        }
    }
}

function initDiagnosticsTabs() {
    // Master Tabs: Robustness vs Portfolio Diagnostics
    const masterPills = document.querySelectorAll('.diag-master-pill');
    masterPills.forEach(pill => {
        pill.addEventListener('click', () => {
            masterPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            
            const targetId = pill.getAttribute('data-panel');
            document.querySelectorAll('.diag-panel').forEach(panel => {
                if (panel.id === targetId) {
                    panel.style.display = 'block';
                    panel.classList.add('active');
                    // Find active subpill and trigger render
                    const activeSub = panel.querySelector('.diag-subpill.active');
                    if (activeSub) {
                        const svId = activeSub.getAttribute('data-subview');
                        triggerSubviewRender(svId);
                    }
                } else {
                    panel.style.display = 'none';
                    panel.classList.remove('active');
                }
            });
            setTimeout(() => {
                window.dispatchEvent(new Event('resize'));
            }, 50);
        });
    });

    // Subtabs in each panel
    const subpills = document.querySelectorAll('.diag-subpill');
    subpills.forEach(subpill => {
        subpill.addEventListener('click', () => {
            const panel = subpill.closest('.diag-panel');
            if (!panel) return;

            panel.querySelectorAll('.diag-subpill').forEach(sp => sp.classList.remove('active'));
            subpill.classList.add('active');

            const targetViewId = subpill.getAttribute('data-subview');
            panel.querySelectorAll('.diag-view-pane').forEach(pane => {
                if (pane.id === targetViewId) {
                    pane.style.display = 'block';
                    pane.classList.add('active');
                } else {
                    pane.style.display = 'none';
                    pane.classList.remove('active');
                }
            });

            triggerSubviewRender(targetViewId);

            setTimeout(() => {
                window.dispatchEvent(new Event('resize'));
            }, 50);
        });
    });

    // Heatmap filter selectors
    const selectTp = document.getElementById('select-heatmap-tp');
    const selectMetric = document.getElementById('select-heatmap-metric');
    if (selectTp) {
        selectTp.addEventListener('change', () => {
            if (_currentDiagnostics && _currentDiagnostics.parameter_sensitivity) {
                renderParameterHeatmap(_currentDiagnostics.parameter_sensitivity);
            }
        });
    }
    if (selectMetric) {
        selectMetric.addEventListener('change', () => {
            if (_currentDiagnostics && _currentDiagnostics.parameter_sensitivity) {
                renderParameterHeatmap(_currentDiagnostics.parameter_sensitivity);
            }
        });
    }

    // On-demand toggle and hero button
    const btnToggleDiag = document.getElementById('btn-toggle-diagnostics');
    if (btnToggleDiag) {
        btnToggleDiag.addEventListener('click', toggleOrCalculateDiagnostics);
    }
    const btnHeroDiag = document.getElementById('btn-run-diagnostics-hero');
    if (btnHeroDiag) {
        btnHeroDiag.addEventListener('click', toggleOrCalculateDiagnostics);
    }

    resetDiagnosticsUI();
}

function renderDiagnosticsSuite(diag) {
    if (!diag) return;
    _currentDiagnostics = diag;

    if (diag.benchmark_comparison) renderBenchmarkComparison(diag.benchmark_comparison);
    if (diag.out_of_sample_split) renderOosSplit(diag.out_of_sample_split);
    if (diag.parameter_sensitivity) renderParameterHeatmap(diag.parameter_sensitivity);
    if (diag.monte_carlo) renderMonteCarlo(diag.monte_carlo);
    if (diag.regime_split) renderRegimeSplit(diag.regime_split);
    if (diag.pnl_distribution) renderPnlDistribution(diag.pnl_distribution);
    if (diag.sector_mcap) renderSectorMcap(diag.sector_mcap);
    if (diag.concurrent_timeline) renderConcurrentTimeline(diag.concurrent_timeline);
    if (diag.rolling_metrics) renderRollingMetrics(diag.rolling_metrics);
    if (diag.position_sizing) renderPositionSizingComparison(diag.position_sizing);
}

function renderBenchmarkComparison(data) {
    const elStratCagr = document.getElementById('kpi-strat-cagr');
    const elNiftyCagr = document.getElementById('kpi-nifty-cagr');
    const elAlpha = document.getElementById('kpi-alpha');
    const elBeta = document.getElementById('kpi-beta');
    const elCorr = document.getElementById('kpi-corr');

    const stratCagr = Number(data.strategy_cagr !== undefined ? data.strategy_cagr : (data.strat_cagr || 0));
    const niftyCagr = Number(data.nifty_cagr || 0);
    const alpha = Number(data.alpha || 0);

    if (elStratCagr) {
        elStratCagr.textContent = `${stratCagr >= 0 ? '+' : ''}${stratCagr.toFixed(2)}%`;
        elStratCagr.className = `diag-kpi-val ${stratCagr >= 0 ? 'text-green' : 'text-red'}`;
    }
    if (elNiftyCagr) {
        elNiftyCagr.textContent = `${niftyCagr >= 0 ? '+' : ''}${niftyCagr.toFixed(2)}%`;
    }
    if (elAlpha) {
        elAlpha.textContent = `${alpha >= 0 ? '+' : ''}${alpha.toFixed(2)}%`;
        elAlpha.className = `diag-kpi-val ${alpha >= 0 ? 'text-green' : 'text-red'}`;
    }
    if (elBeta) {
        elBeta.textContent = Number(data.beta || 0).toFixed(2);
    }
    if (elCorr) {
        elCorr.textContent = Number(data.correlation || 0).toFixed(2);
    }

    const container = document.getElementById('chart-benchmark-container');
    const stratEquity = data.strategy_equity || data.strat_rebased;
    const niftyEquity = data.nifty_equity || data.nifty_rebased;

    if (container && window.Plotly && data.dates && data.dates.length > 0 && stratEquity && niftyEquity) {
        const traceStrat = {
            x: data.dates,
            y: stratEquity,
            name: 'Strategy Equity (Base 100)',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#3b82f6', width: 2.5 }
        };
        const traceNifty = {
            x: data.dates,
            y: niftyEquity,
            name: 'Nifty 50 Buy & Hold (Base 100)',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#f59e0b', width: 1.8, dash: 'dash' }
        };

        const layout = {
            ...PLOTLY_DARK_LAYOUT,
            title: false,
            hovermode: 'x unified',
            yaxis: {
                ...PLOTLY_DARK_LAYOUT.yaxis,
                title: 'Relative Performance (Base 100)'
            },
            legend: {
                ...PLOTLY_DARK_LAYOUT.legend,
                orientation: 'h',
                x: 0,
                y: 1.12
            }
        };

        Plotly.react(container, [traceStrat, traceNifty], layout, PLOTLY_CONFIG);
    }
}

function renderOosSplit(data) {
    const elInfo = document.getElementById('oos-split-info');
    const elBadge = document.getElementById('oos-degradation-badge');
    const tbody = document.getElementById('tbody-oos-comparison');

    const is = data.in_sample || {};
    const oos = data.out_of_sample || {};
    const ratio = Number(data.degradation_ratio || 0);

    if (elInfo) {
        if (data.in_sample) {
            elInfo.textContent = `In-Sample (65%): ${is.trades || 0} trades [${is.start_date || '-'} to ${is.end_date || '-'}] | Out-of-Sample (35%): ${oos.trades || 0} trades [${oos.start_date || '-'} to ${oos.end_date || '-'}]`;
        } else {
            elInfo.textContent = `In-Sample (65%): ${data.is_trades_count || 0} trades [${data.is_period || '-'}] | Out-of-Sample (35%): ${data.oos_trades_count || 0} trades [${data.oos_period || '-'}]`;
        }
    }
    if (elBadge) {
        const status = data.status ? ` (${data.status})` : '';
        elBadge.textContent = `${(ratio * 100).toFixed(1)}% Retention${status}`;
        elBadge.className = `badge-tag ${ratio >= 0.7 ? 'badge-green' : (ratio >= 0.5 ? 'badge-yellow' : 'badge-red')}`;
    }
    if (tbody) {
        if (data.in_sample && data.out_of_sample) {
            const metrics = [
                { metric: 'Total Trades', is: `${is.trades}`, oos: `${oos.trades}`, retention: '-' },
                { metric: 'Win Rate %', is: `${is.win_pct}%`, oos: `${oos.win_pct}%`, retention: `${is.win_pct > 0 ? (oos.win_pct / is.win_pct * 100).toFixed(1) : 0}%` },
                { metric: 'Profit Factor', is: `${Number(is.profit_factor).toFixed(2)}`, oos: `${Number(oos.profit_factor).toFixed(2)}`, retention: `${is.profit_factor > 0 ? (oos.profit_factor / is.profit_factor * 100).toFixed(1) : 0}%` },
                { metric: 'CAGR %', is: `${is.cagr_pct}%`, oos: `${oos.cagr_pct}%`, retention: `${is.cagr_pct > 0 ? (oos.cagr_pct / is.cagr_pct * 100).toFixed(1) : 0}%` },
                { metric: 'Max Drawdown %', is: `${is.max_drawdown}%`, oos: `${oos.max_drawdown}%`, retention: '-' },
                { metric: 'Total Net Profit', is: formatRupeeVal(is.total_profit), oos: formatRupeeVal(oos.total_profit), retention: '-' },
                { metric: 'Expectancy Ratio', is: `${Number(is.expectancy).toFixed(2)}`, oos: `${Number(oos.expectancy).toFixed(2)}`, retention: '-' },
                { metric: 'Sharpe Ratio', is: `${Number(is.sharpe).toFixed(2)}`, oos: `${Number(oos.sharpe).toFixed(2)}`, retention: '-' }
            ];
            tbody.innerHTML = metrics.map(m => `
                <tr>
                    <td style="font-weight: 600; color: #cbd5e1;">${m.metric}</td>
                    <td style="color: #60a5fa; font-weight: 500;">${m.is}</td>
                    <td style="color: #c084fc; font-weight: 500;">${m.oos}</td>
                    <td><span class="badge-tag ${parseFloat(m.retention) >= 70 ? 'badge-green' : (parseFloat(m.retention) >= 50 ? 'badge-yellow' : 'badge-neutral')}">${m.retention}</span></td>
                </tr>
            `).join('');
        } else if (data.metrics) {
            tbody.innerHTML = data.metrics.map(m => {
                const retNum = parseFloat(m.retention);
                let badgeClass = 'badge-green';
                if (isNaN(retNum) || retNum < 50) badgeClass = 'badge-red';
                else if (retNum < 70) badgeClass = 'badge-yellow';

                return `
                    <tr>
                        <td style="font-weight: 600; color: #cbd5e1;">${m.metric}</td>
                        <td style="color: #60a5fa; font-weight: 500;">${m.is}</td>
                        <td style="color: #c084fc; font-weight: 500;">${m.oos}</td>
                        <td><span class="badge-tag ${badgeClass}">${m.retention}</span></td>
                    </tr>
                `;
            }).join('');
        }
    }
}

function renderParameterHeatmap(data) {
    const container = document.getElementById('chart-heatmap-container');
    const grids = data.grids || data.matrices;
    if (!container || !window.Plotly || !grids) return;

    const selectTp = document.getElementById('select-heatmap-tp');
    const selectMetric = document.getElementById('select-heatmap-metric');
    const selectedTp = (selectTp && selectTp.value) || data.default_tp || '100%';
    const selectedMetric = (selectMetric && selectMetric.value) || 'profit_factor';

    const matrixData = grids[selectedTp] ? grids[selectedTp][selectedMetric] : null;
    if (!matrixData) return;

    const emaArr = data.ema_values || data.ema_lengths || [20, 25, 30, 35, 40];
    const rsiArr = data.rsi_values || data.rsi_thresholds || [70, 75, 80, 85];
    const xLabels = emaArr.map(l => `EMA ${l}`);
    const yLabels = rsiArr.map(r => `RSI > ${r}`);

    const annotations = [];
    for (let i = 0; i < yLabels.length; i++) {
        for (let j = 0; j < xLabels.length; j++) {
            if (matrixData[i] && matrixData[i][j] !== undefined) {
                const val = matrixData[i][j];
                const textVal = selectedMetric === 'profit_factor' 
                    ? Number(val).toFixed(2) 
                    : formatRupeeVal(val);

                annotations.push({
                    x: xLabels[j],
                    y: yLabels[i],
                    text: textVal,
                    font: {
                        family: 'Outfit, sans-serif',
                        size: 11,
                        color: '#ffffff',
                        weight: 600
                    },
                    showarrow: false
                });
            }
        }
    }

    const colorscale = selectedMetric === 'profit_factor'
        ? [
            [0.0, '#1e1b4b'],
            [0.3, '#312e81'],
            [0.6, '#2563eb'],
            [1.0, '#10b981']
          ]
        : [
            [0.0, '#7f1d1d'],
            [0.4, '#1e293b'],
            [0.7, '#065f46'],
            [1.0, '#10b981']
          ];

    const trace = {
        z: matrixData,
        x: xLabels,
        y: yLabels,
        type: 'heatmap',
        colorscale: colorscale,
        showscale: true,
        colorbar: {
            tickfont: { color: '#94a3b8' },
            outlinecolor: 'rgba(0,0,0,0)',
            len: 0.8
        },
        hoverongaps: false
    };

    const layout = {
        ...PLOTLY_DARK_LAYOUT,
        annotations: annotations,
        xaxis: {
            ...PLOTLY_DARK_LAYOUT.xaxis,
            type: 'category',
            title: 'Trailing Exit EMA Length'
        },
        yaxis: {
            ...PLOTLY_DARK_LAYOUT.yaxis,
            type: 'category',
            title: 'Entry RSI Threshold'
        }
    };

    Plotly.react(container, [trace], layout, PLOTLY_CONFIG);
}

function renderMonteCarlo(data) {
    const elMedian = document.getElementById('kpi-mc-median-dd');
    const elP95 = document.getElementById('kpi-mc-p95-dd');
    const elP99 = document.getElementById('kpi-mc-p99-dd');
    const elProb = document.getElementById('kpi-mc-prob-20');

    const stats = data.stats || data.kpis || {};
    const medianDd = stats.median_mdd !== undefined ? stats.median_mdd : (stats.median_max_dd || 0);
    const p95Dd = stats.p95_worst_case_mdd !== undefined ? stats.p95_worst_case_mdd : (stats.p95_worst_dd || 0);
    const p99Dd = stats.p99_stress_mdd !== undefined ? stats.p99_stress_mdd : (stats.p99_stress_dd || 0);
    const prob20 = stats.prob_dd_over_20_pct !== undefined ? `${stats.prob_dd_over_20_pct}%` : (stats.prob_dd_over_20 || '0.0%');

    if (elMedian) elMedian.textContent = formatRupeeVal(medianDd);
    if (elP95) elP95.textContent = formatRupeeVal(p95Dd);
    if (elP99) elP99.textContent = formatRupeeVal(p99Dd);
    if (elProb) elProb.textContent = prob20;

    const container = document.getElementById('chart-montecarlo-container');
    const fanCurves = data.percentiles || data.fan_curves;
    const x = data.steps || data.trade_indices;

    if (container && window.Plotly && fanCurves && x) {
        const traces = [
            {
                x: x,
                y: fanCurves.p5,
                type: 'scatter',
                mode: 'lines',
                line: { color: 'rgba(59, 130, 246, 0.25)', width: 1 },
                name: '5th %ile (Worst 5%)',
                showlegend: false
            },
            {
                x: x,
                y: fanCurves.p95,
                type: 'scatter',
                mode: 'lines',
                fill: 'tonexty',
                fillcolor: 'rgba(59, 130, 246, 0.10)',
                line: { color: 'rgba(59, 130, 246, 0.25)', width: 1 },
                name: '90% Confidence Band (5th - 95th %ile)'
            },
            {
                x: x,
                y: fanCurves.p25,
                type: 'scatter',
                mode: 'lines',
                line: { color: 'rgba(99, 102, 241, 0.4)', width: 1 },
                name: '25th %ile',
                showlegend: false
            },
            {
                x: x,
                y: fanCurves.p75,
                type: 'scatter',
                mode: 'lines',
                fill: 'tonexty',
                fillcolor: 'rgba(99, 102, 241, 0.20)',
                line: { color: 'rgba(99, 102, 241, 0.4)', width: 1 },
                name: '50% Confidence Band (25th - 75th %ile)'
            },
            {
                x: x,
                y: fanCurves.p50,
                type: 'scatter',
                mode: 'lines',
                line: { color: '#06b6d4', width: 2.8 },
                name: 'Median Simulation (50th %ile)'
            }
        ];

        const layout = {
            ...PLOTLY_DARK_LAYOUT,
            title: false,
            hovermode: 'x unified',
            xaxis: {
                ...PLOTLY_DARK_LAYOUT.xaxis,
                type: 'linear',
                title: 'Trades Resampled Sequence'
            },
            yaxis: {
                ...PLOTLY_DARK_LAYOUT.yaxis,
                title: 'Simulated Portfolio Equity (₹)',
                tickformat: 's'
            },
            legend: {
                ...PLOTLY_DARK_LAYOUT.legend,
                orientation: 'h',
                x: 0,
                y: 1.12
            }
        };

        Plotly.react(container, traces, layout, PLOTLY_CONFIG);
    }
}

function renderRegimeSplit(data) {
    const tbody = document.getElementById('tbody-regime');
    if (tbody && data.regimes) {
        tbody.innerHTML = data.regimes.map(r => {
            const regimeIcon = r.regime.includes('Bull') ? '🐂' : (r.regime.includes('Bear') ? '🐻' : '↔️');
            const winRate = Number(r.win_pct !== undefined ? r.win_pct : (r.win_rate || 0));
            const netPnl = Number(r.total_profit !== undefined ? r.total_profit : (r.net_pnl || 0));
            const avgP = Number(r.avg_profit || 0);
            const pf = Number(r.profit_factor || 0);

            return `
                <tr>
                    <td style="font-weight: 600; color: #cbd5e1;">${regimeIcon} ${r.regime}</td>
                    <td>${r.trades}</td>
                    <td class="${winRate >= 50 ? 'text-green' : 'text-neutral'}">${winRate.toFixed(1)}%</td>
                    <td class="${pf >= 1.5 ? 'text-green' : (pf < 1.0 ? 'text-red' : 'text-neutral')}">${pf.toFixed(2)}</td>
                    <td class="${netPnl >= 0 ? 'text-green' : 'text-red'}">${formatRupeeVal(netPnl)}</td>
                    <td class="${avgP >= 0 ? 'text-green' : 'text-red'}">${formatRupeeVal(avgP)}</td>
                </tr>
            `;
        }).join('');
    }

    const container = document.getElementById('chart-regime-container');
    if (container && window.Plotly && data.regimes) {
        const netPnls = data.regimes.map(r => Number(r.total_profit !== undefined ? r.total_profit : (r.net_pnl || 0)));
        const trace = {
            x: data.regimes.map(r => r.regime),
            y: netPnls,
            type: 'bar',
            marker: {
                color: netPnls.map(p => p >= 0 ? '#10b981' : '#ef4444'),
                line: { color: 'rgba(255, 255, 255, 0.1)', width: 1 }
            }
        };

        const layout = {
            ...PLOTLY_DARK_LAYOUT,
            title: false,
            yaxis: {
                ...PLOTLY_DARK_LAYOUT.yaxis,
                title: 'Total Net PnL (₹)',
                tickformat: 's'
            }
        };

        Plotly.react(container, [trace], layout, PLOTLY_CONFIG);
    }
}

function renderPnlDistribution(data) {
    const elSkew = document.getElementById('kpi-dist-skew');
    const elKurt = document.getElementById('kpi-dist-kurt');
    const elDesc = document.getElementById('kpi-dist-desc');

    if (elSkew) {
        const val = Number(data.skewness || 0);
        elSkew.textContent = `${val >= 0 ? '+' : ''}${val.toFixed(2)}`;
        elSkew.className = `diag-kpi-val ${val >= 0 ? 'text-green' : 'text-red'}`;
    }
    if (elKurt) elKurt.textContent = Number(data.kurtosis || 0).toFixed(2);
    if (elDesc) elDesc.textContent = data.fat_tail_comment || data.fat_tail_diagnosis || '-';

    const pnlContainer = document.getElementById('chart-pnl-hist-container');
    if (pnlContainer && window.Plotly) {
        if (data.histogram) {
            const traceHist = {
                x: data.histogram.map(h => h.bin),
                y: data.histogram.map(h => h.count),
                type: 'bar',
                marker: {
                    color: data.histogram.map(h => h.bin.includes('-') ? '#ef4444' : '#10b981'),
                    opacity: 0.85
                }
            };
            const layoutHist = {
                ...PLOTLY_DARK_LAYOUT,
                title: { text: 'P&L Return Bins', font: { color: '#cbd5e1', size: 12 } },
                xaxis: { ...PLOTLY_DARK_LAYOUT.xaxis, title: 'Return Bins' },
                yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: 'Number of Trades' }
            };
            Plotly.react(pnlContainer, [traceHist], layoutHist, PLOTLY_CONFIG);
        } else if (data.pnl_values) {
            const tracePnl = {
                x: data.pnl_values,
                type: 'histogram',
                nbinsx: 35,
                marker: {
                    color: '#3b82f6',
                    line: { color: '#1d4ed8', width: 1 },
                    opacity: 0.85
                }
            };
            const layoutPnl = {
                ...PLOTLY_DARK_LAYOUT,
                title: { text: 'P&L Distribution (₹)', font: { color: '#cbd5e1', size: 12 } },
                xaxis: { ...PLOTLY_DARK_LAYOUT.xaxis, title: 'Trade Profit / Loss (₹)' },
                yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: 'Number of Trades' }
            };
            Plotly.react(pnlContainer, [tracePnl], layoutPnl, PLOTLY_CONFIG);
        }
    }

    const rContainer = document.getElementById('chart-rmult-hist-container');
    if (rContainer && window.Plotly && data.r_multiples) {
        const traceR = {
            x: data.r_multiples,
            type: 'histogram',
            nbinsx: 30,
            marker: {
                color: '#8b5cf6',
                line: { color: '#6d28d9', width: 1 },
                opacity: 0.85
            }
        };
        const layoutR = {
            ...PLOTLY_DARK_LAYOUT,
            title: { text: 'R-Multiple Distribution', font: { color: '#cbd5e1', size: 12 } },
            xaxis: { ...PLOTLY_DARK_LAYOUT.xaxis, title: 'R-Multiple (Trade Return ÷ Risk)' },
            yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: 'Number of Trades' }
        };
        Plotly.react(rContainer, [traceR], layoutR, PLOTLY_CONFIG);
    }
}

function renderSectorMcap(data) {
    const donutContainer = document.getElementById('chart-mcap-donut-container');
    const mcapTiers = data.market_cap || data.mcap_tiers;
    if (donutContainer && window.Plotly && mcapTiers) {
        const traceDonut = {
            type: 'pie',
            hole: 0.55,
            labels: mcapTiers.map(t => t.tier),
            values: mcapTiers.map(t => t.trades !== undefined ? t.trades : t.count),
            marker: {
                colors: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899']
            },
            textinfo: 'label+percent',
            textposition: 'outside',
            showlegend: false
        };
        const layoutDonut = {
            ...PLOTLY_DARK_LAYOUT,
            margin: { l: 20, r: 20, t: 20, b: 20 }
        };
        Plotly.react(donutContainer, [traceDonut], layoutDonut, PLOTLY_CONFIG);
    }

    const barContainer = document.getElementById('chart-sector-bar-container');
    if (barContainer && window.Plotly && data.sectors) {
        const topSectors = [...data.sectors].sort((a, b) => {
            const pA = a.profit !== undefined ? a.profit : (a.net_pnl || 0);
            const pB = b.profit !== undefined ? b.profit : (b.net_pnl || 0);
            return pB - pA;
        }).slice(0, 8);

        const profits = topSectors.map(s => Number(s.profit !== undefined ? s.profit : (s.net_pnl || 0)));
        const traceBar = {
            type: 'bar',
            orientation: 'h',
            y: topSectors.map(s => s.sector).reverse(),
            x: profits.reverse(),
            marker: {
                color: profits.map(p => p >= 0 ? '#10b981' : '#ef4444').reverse()
            }
        };
        const layoutBar = {
            ...PLOTLY_DARK_LAYOUT,
            margin: { l: 110, r: 25, t: 15, b: 35 },
            xaxis: { ...PLOTLY_DARK_LAYOUT.xaxis, title: 'Net Profit (₹)', tickformat: 's' }
        };
        Plotly.react(barContainer, [traceBar], layoutBar, PLOTLY_CONFIG);
    }

    const tbody = document.getElementById('tbody-sector-breakdown');
    if (tbody && data.sectors) {
        tbody.innerHTML = data.sectors.map(s => {
            const p = Number(s.profit !== undefined ? s.profit : (s.net_pnl || 0));
            const winRate = Number(s.win_pct !== undefined ? s.win_pct : (s.win_rate || 0));
            return `
                <tr>
                    <td style="font-weight: 600; color: #cbd5e1;">${s.sector}</td>
                    <td>${s.trades}</td>
                    <td class="${winRate >= 50 ? 'text-green' : 'text-neutral'}">${winRate.toFixed(1)}%</td>
                    <td class="${p >= 0 ? 'text-green' : 'text-red'}">${formatRupeeVal(p)}</td>
                </tr>
            `;
        }).join('');
    }
}

function renderConcurrentTimeline(data) {
    const elPeak = document.getElementById('kpi-timeline-peak-pos');
    const elAvg = document.getElementById('kpi-timeline-avg-util');
    const elDesc = document.getElementById('kpi-timeline-desc');

    const peakPos = data.peak_positions !== undefined ? data.peak_positions : (data.peak_concurrent || 0);
    const avgUtil = data.avg_utilization !== undefined ? data.avg_utilization : (data.avg_utilization_pct || 0);

    if (elPeak) elPeak.textContent = `${peakPos} Positions`;
    if (elAvg) elAvg.textContent = `${Number(avgUtil).toFixed(1)}%`;
    if (elDesc && data.insight) elDesc.textContent = data.insight;

    const container = document.getElementById('chart-concurrent-timeline-container');
    const positions = data.positions || data.concurrent_positions;
    const utilization = data.utilization_pct || data.capital_deployed;

    if (container && window.Plotly && data.dates && positions) {
        const tracePositions = {
            x: data.dates,
            y: positions,
            name: 'Active Positions Count',
            type: 'scatter',
            mode: 'lines',
            fill: 'tozeroy',
            fillcolor: 'rgba(139, 92, 246, 0.15)',
            line: { color: '#8b5cf6', width: 2 }
        };

        const traces = [tracePositions];
        if (utilization) {
            traces.push({
                x: data.dates,
                y: utilization,
                name: 'Capital Deployed / Utilization %',
                yaxis: 'y2',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#10b981', width: 2 }
            });
        }

        const layout = {
            ...PLOTLY_DARK_LAYOUT,
            title: false,
            hovermode: 'x unified',
            yaxis: {
                ...PLOTLY_DARK_LAYOUT.yaxis,
                title: 'Open Positions Count',
                side: 'left'
            },
            yaxis2: {
                ...PLOTLY_DARK_LAYOUT.yaxis,
                title: 'Capital / Utilization',
                side: 'right',
                overlaying: 'y',
                gridcolor: 'rgba(0,0,0,0)',
                tickformat: 's'
            },
            legend: {
                ...PLOTLY_DARK_LAYOUT.legend,
                orientation: 'h',
                x: 0,
                y: 1.12
            }
        };

        Plotly.react(container, traces, layout, PLOTLY_CONFIG);
    }
}

function renderRollingMetrics(data) {
    const container = document.getElementById('chart-rolling-metrics-container');
    if (container && window.Plotly && data.dates && data.dates.length > 0) {
        const traceSharpe6m = {
            x: data.dates,
            y: data.sharpe_6m,
            name: 'Rolling 6M Sharpe',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#60a5fa', width: 2 }
        };
        const traceSharpe12m = {
            x: data.dates,
            y: data.sharpe_12m,
            name: 'Rolling 12M Sharpe',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#3b82f6', width: 2.5 }
        };
        const traceWin6m = {
            x: data.dates,
            y: data.win_rate_6m,
            name: 'Rolling 6M Win %',
            yaxis: 'y2',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#34d399', width: 1.8, dash: 'dot' }
        };
        const traceWin12m = {
            x: data.dates,
            y: data.win_rate_12m,
            name: 'Rolling 12M Win %',
            yaxis: 'y2',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#059669', width: 2, dash: 'dash' }
        };

        const layout = {
            ...PLOTLY_DARK_LAYOUT,
            title: false,
            hovermode: 'x unified',
            yaxis: {
                ...PLOTLY_DARK_LAYOUT.yaxis,
                title: 'Sharpe Ratio'
            },
            yaxis2: {
                ...PLOTLY_DARK_LAYOUT.yaxis,
                title: 'Win Rate (%)',
                side: 'right',
                overlaying: 'y',
                gridcolor: 'rgba(0,0,0,0)',
                range: [0, 100]
            },
            legend: {
                ...PLOTLY_DARK_LAYOUT.legend,
                orientation: 'h',
                x: 0,
                y: 1.12
            }
        };

        Plotly.react(container, [traceSharpe6m, traceSharpe12m, traceWin6m, traceWin12m], layout, PLOTLY_CONFIG);
    }
}

function renderPositionSizingComparison(data) {
    const tbody = document.getElementById('tbody-sizing-comparison');
    if (tbody && data.models) {
        const rows = [
            { name: 'Fixed ₹100,000 / Trade (Current Baseline)', model: data.models.fixed },
            { name: 'Compounding 5% Active Equity', model: data.models.compounding },
            { name: 'Volatility-Scaled (0.5% Risk / Trade)', model: data.models.volatility_scaled }
        ];

        tbody.innerHTML = rows.map(r => {
            const m = r.model || {};
            return `
                <tr>
                    <td style="font-weight: 600; color: #cbd5e1;">${r.name}</td>
                    <td class="${(m.net_profit || 0) >= 0 ? 'text-green' : 'text-red'}">${formatRupeeVal(m.net_profit || 0)}</td>
                    <td class="${(m.cagr_pct || 0) >= 0 ? 'text-green' : 'text-red'}">${Number(m.cagr_pct || 0).toFixed(2)}%</td>
                    <td class="text-red">${Number(m.max_dd_pct || 0).toFixed(2)}%</td>
                </tr>
            `;
        }).join('');
    }

    const container = document.getElementById('chart-sizing-comparison-container');
    if (container && window.Plotly && data.dates) {
        const traces = [
            {
                x: data.dates,
                y: data.fixed_capital_curve,
                name: 'Fixed ₹100k / Trade',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#94a3b8', width: 1.8 }
            },
            {
                x: data.dates,
                y: data.compounding_equity_curve,
                name: 'Compounding 5% Equity',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#3b82f6', width: 2.5 }
            },
            {
                x: data.dates,
                y: data.volatility_scaled_curve,
                name: 'Volatility-Scaled (0.5% Risk)',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#10b981', width: 2.5 }
            }
        ];

        const layout = {
            ...PLOTLY_DARK_LAYOUT,
            title: false,
            hovermode: 'x unified',
            yaxis: {
                ...PLOTLY_DARK_LAYOUT.yaxis,
                title: 'Portfolio Equity (₹)',
                tickformat: 's'
            },
            legend: {
                ...PLOTLY_DARK_LAYOUT.legend,
                orientation: 'h',
                x: 0,
                y: 1.12
            }
        };

        Plotly.react(container, traces, layout, PLOTLY_CONFIG);
    }
}

// App Initialization
document.addEventListener('DOMContentLoaded', async () => {
    initTabs();
    initWatchlistUpload();
    initEventListeners();
    initGenAITemplateModal();
    initFundamentalsSystem();
    initDailyCacheSystem();
    initDiagnosticsTabs();
    
    // Pre-cache all tickers in background for instant autosuggest
    loadAllSymbols();

    // Load initial data
    await loadStatus();
    await loadZerodhaStatus();
    await loadDates();
    await loadStrategies();
    await loadBacktestStrategies();
    
    // Ensure default view is Quant Screener tab
    switchTab('screener');
});

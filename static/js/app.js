/**
 * ChethanQuant Stock Screener & Backtester - Client Application
 * Multi-Timeframe Screening, DuckDB Parquet Integration, Corporate Action Adjustments, and Interactive Plotly Charts.
 */

// Application State
const AppState = {
    status: null,
    zerodhaStatus: null,
    dates: [],
    strategies: [],
    currentDate: null,
    selectedSegment: 'nifty50',
    selectedTimeframe: '1d',
    chartTimeframe: '1d',
    watchlistSymbols: [],
    screenerResults: [],
    currentChartSymbol: 'RELIANCE',
    activeTab: 'screener',
    currentStrategyIdx: 0,
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
    btBtnRunScreener: document.getElementById('bt-btn-run-screener'),
    btTimeframeSelect: document.getElementById('bt-timeframe-select'),
    btSegmentSelect: document.getElementById('bt-segment-select'),
    btStrategySelect: document.getElementById('bt-strategy-select'),
    btStrategyNameInput: document.getElementById('bt-strategy-name-input'),
    btBtnSaveStrategy: document.getElementById('bt-btn-save-strategy'),
    btBtnDeleteStrategy: document.getElementById('bt-btn-delete-strategy'),
    btScreenStartDate: document.getElementById('bt-screen-start-date'),
    btScreenEndDate: document.getElementById('bt-screen-end-date'),
    btScreenerLoading: document.getElementById('bt-screener-loading'),
    btScreenerResultsContainer: document.getElementById('bt-screener-results-container'),
    btScreenerMatchesSummary: document.getElementById('bt-screener-matches-summary'),
    btScreenerMetaSummary: document.getElementById('bt-screener-meta-summary'),
    btResultsTableThead: document.getElementById('bt-results-table-thead'),
    btResultsTableBody: document.getElementById('bt-results-table-body'),
    btBtnExportExcel: document.getElementById('bt-btn-export-excel'),
    
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
            
            if (data.oldest_date && data.latest_date) {
                if (elements.screenStartDate) elements.screenStartDate.value = data.oldest_date;
                if (elements.screenEndDate) elements.screenEndDate.value = data.latest_date;
                if (elements.btScreenStartDate) elements.btScreenStartDate.value = data.oldest_date;
                if (elements.btScreenEndDate) elements.btScreenEndDate.value = data.latest_date;
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
            <td><span class="stock-pill" onclick="openChartForSymbol('${item.Symbol}')">${item.Symbol}</span></td>
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
            <td><span class="stock-pill" onclick="openChartForSymbol('${item.Symbol}')">${item.Symbol}</span></td>
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
            <td><span class="stock-pill" onclick="openChartForSymbol('${item.Symbol}')">${item.Symbol}</span></td>
            <td style="font-family: var(--font-mono); font-weight: 600;">₹${Number(item.Close).toFixed(2)}</td>
            <td style="font-weight: 600; color: #a5b4fc;">${formatNumber(item.Volume)}</td>
        `;
        elements.volumeTableBody.appendChild(tr);
    });
}

// Strategies Management
function populateStrategySelects() {
    if (elements.strategySelect) elements.strategySelect.innerHTML = '';
    if (elements.btStrategySelect) elements.btStrategySelect.innerHTML = '';
    
    AppState.strategies.forEach((strat, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = strat.name;
        if (elements.strategySelect) elements.strategySelect.appendChild(opt);
        
        if (elements.btStrategySelect) {
            const optBt = document.createElement('option');
            optBt.value = idx;
            optBt.textContent = strat.name;
            elements.btStrategySelect.appendChild(optBt);
        }
    });
}

async function loadStrategies(targetStrategyName = null) {
    try {
        const res = await fetch('/api/strategies');
        const data = await res.json();
        AppState.strategies = data.strategies || [];
        
        populateStrategySelects();
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
            if (elements.btStrategySelect) elements.btStrategySelect.value = selectIdx;
            selectStrategy(selectIdx, 'both');
        }
    } catch (err) {
        console.error('Error fetching strategies:', err);
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
        btn.title = `Click to load "${strat.name}" into sandbox`;
        
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            // Switch to screener tab if user is on charts or manager
            if (AppState.activeTab !== 'screener') {
                switchTab('screener');
            }
            selectStrategy(idx, 'both');
            showToast(`Loaded "${strat.name}" into sandbox`, 'info');
            if (elements.codeEditor) {
                elements.codeEditor.focus();
            }
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

function selectStrategy(index, target = 'screener') {
    AppState.currentStrategyIdx = index;
    const strat = AppState.strategies[index];
    if (strat) {
        if (target === 'screener' || target === 'both') {
            if (elements.codeEditor) elements.codeEditor.value = strat.code;
            if (elements.strategyNameInput) elements.strategyNameInput.value = strat.name;
            if (elements.strategySelect) elements.strategySelect.value = index;
        }
        if (target === 'backtest' || target === 'both') {
            if (elements.btCodeEditor) elements.btCodeEditor.value = strat.code;
            if (elements.btStrategyNameInput) elements.btStrategyNameInput.value = strat.name;
            if (elements.btStrategySelect) elements.btStrategySelect.value = index;
        }
        updateActiveStrategyLink(index);
    }
}

// Custom Stock Screener & Backtest Across Timeframes
async function runScreener(isBacktest = false) {
    const codeEl = isBacktest ? elements.btCodeEditor : elements.codeEditor;
    const btnRun = isBacktest ? elements.btBtnRunScreener : elements.btnRunScreener;
    const loadingEl = isBacktest ? elements.btScreenerLoading : elements.screenerLoading;
    const resultsContainerEl = isBacktest ? elements.btScreenerResultsContainer : elements.screenerResultsContainer;
    const segSelect = isBacktest ? elements.btSegmentSelect : elements.segmentSelect;
    const tfSelect = isBacktest ? elements.btTimeframeSelect : elements.timeframeSelect;
    const startEl = isBacktest ? elements.btScreenStartDate : elements.screenStartDate;
    const endEl = isBacktest ? elements.btScreenEndDate : elements.screenEndDate;

    const code = codeEl ? codeEl.value.trim() : '';
    if (!code) {
        showToast(isBacktest ? 'Please enter Python strategy logic' : 'Please enter Python screen(df) function code', 'error');
        return;
    }
    
    const segment = segSelect ? segSelect.value : 'nifty50';
    const timeframe = tfSelect ? tfSelect.value : '1d';
    const startDate = startEl ? startEl.value || null : null;
    const endDate = endEl ? endEl.value || null : null;
    
    if (btnRun) btnRun.disabled = true;
    if (loadingEl) loadingEl.style.display = 'block';
    if (resultsContainerEl) resultsContainerEl.style.display = 'none';
    
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
                end_date: endDate
            })
        });
        
        const data = await res.json();
        
        if (data.status === 'error') {
            showToast(data.message, 'error');
        } else {
            AppState.screenerResults = data.flat_matches || [];
            showToast(`${isBacktest ? 'Backtest' : 'Screening'} complete: ${data.total_matches} matches on ${timeframe} in ${data.duration_seconds}s`, 'success');
            renderScreenerResults(data, isBacktest);
        }
    } catch (err) {
        showToast(`Failed to execute ${isBacktest ? 'backtest' : 'screener'}: ${err.message}`, 'error');
    } finally {
        if (btnRun) btnRun.disabled = false;
        if (loadingEl) loadingEl.style.display = 'none';
    }
}

function renderScreenerResults(data, isBacktest = false) {
    const resultsContainer = isBacktest ? elements.btScreenerResultsContainer : elements.screenerResultsContainer;
    const matchesSummary = isBacktest ? elements.btScreenerMatchesSummary : elements.screenerMatchesSummary;
    const metaSummary = isBacktest ? elements.btScreenerMetaSummary : elements.screenerMetaSummary;
    const thead = isBacktest ? elements.btResultsTableThead : elements.resultsTableThead;
    const tbody = isBacktest ? elements.btResultsTableBody : elements.resultsTableBody;
    const btnExportExcel = isBacktest ? elements.btBtnExportExcel : elements.btnExportExcel;

    if (!resultsContainer) return;
    resultsContainer.style.display = 'block';
    if (matchesSummary) matchesSummary.textContent = `${data.total_matches} Matches Found (${data.timeframe.toUpperCase()})`;
    if (metaSummary) metaSummary.textContent = `Scanned ${data.total_symbols_scanned} stocks on [${data.timeframe}] across ${data.dates_with_matches} periods in ${data.duration_seconds}s`;
    
    const matches = data.flat_matches || [];
    if (matches.length === 0) {
        if (thead) thead.innerHTML = `<tr><th>Status</th></tr>`;
        if (tbody) tbody.innerHTML = `<tr><td style="text-align: center; color: var(--text-muted); padding: 2rem;">No stocks matched criteria on timeframe ${data.timeframe}.</td></tr>`;
        if (btnExportExcel) btnExportExcel.disabled = true;
        if (elements.btnExportCsv) elements.btnExportCsv.disabled = true;
        return;
    }
    
    if (btnExportExcel) btnExportExcel.disabled = false;
    if (elements.btnExportCsv) elements.btnExportCsv.disabled = false;
    
    // Dynamic custom data columns (filtering out unwanted columns: Avg_Volume_20, Close, Monthly_R2, Volume, Volume_Ratio, in_trade, stage, stop_loss)
    const unwantedCols = new Set([
        'avg_volume_20', 'close', 'monthly_r2', 'volume', 'volume_ratio',
        'in_trade', 'stage', 'stop_loss', 'entries', 'signal'
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
        if (a.toLowerCase() === 'r2_cross_date') return -1;
        if (b.toLowerCase() === 'r2_cross_date') return 1;
        return a.localeCompare(b);
    });
    
    // Render thead
    let thHtml = `
        <tr>
            <th>Date / Time</th>
            <th>Symbol</th>
            <th>Close Price</th>
            <th>Change (%)</th>
    `;
    customKeysArr.forEach(k => {
        const headerName = k.replace(/_/g, ' ');
        thHtml += `<th>${headerName}</th>`;
    });
    thHtml += `<th>Action</th></tr>`;
    if (thead) thead.innerHTML = thHtml;
    
    // Render tbody
    if (tbody) {
        tbody.innerHTML = '';
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
            
            let rowHtml = `
                <td style="color: var(--text-muted); font-family: var(--font-mono);">${row.Date}</td>
                <td><span class="stock-pill" onclick="openChartForSymbol('${row.Symbol}', '${data.timeframe}')">${row.Symbol}</span></td>
                <td style="font-family: var(--font-mono); font-weight: 600;">₹${Number(row.Close).toFixed(2)}</td>
                <td>${changeBadge}</td>
            `;
            
            customKeysArr.forEach(k => {
                const val = row.custom_data ? row.custom_data[k] : '-';
                rowHtml += `<td style="font-family: var(--font-mono); color: #c7d2fe;">${val !== undefined ? val : '-'}</td>`;
            });
            
            rowHtml += `
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="openChartForSymbol('${row.Symbol}', '${data.timeframe}')">
                        📈 Chart
                    </button>
                </td>
            `;
            
            tr.innerHTML = rowHtml;
            tbody.appendChild(tr);
        });
    }
}

// Export Screener Results
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

// Save or Delete Strategy
async function saveCurrentStrategy(isBacktest = false) {
    const nameInput = isBacktest ? elements.btStrategyNameInput : elements.strategyNameInput;
    const editor = isBacktest ? elements.btCodeEditor : elements.codeEditor;
    const name = nameInput ? nameInput.value.trim() : '';
    const code = editor ? editor.value.trim() : '';
    
    if (!name || !code) {
        showToast('Please provide both a strategy name and code', 'error');
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
        showToast(`Error saving strategy: ${err.message}`, 'error');
    }
}

async function deleteCurrentStrategy(isBacktest = false) {
    const nameInput = isBacktest ? elements.btStrategyNameInput : elements.strategyNameInput;
    const name = nameInput ? nameInput.value.trim() : '';
    if (!name) return;
    
    if (!confirm(`Are you sure you want to delete strategy template "${name}"?`)) return;
    
    try {
        const res = await fetch(`/api/strategies/${encodeURIComponent(name)}`, {
            method: 'DELETE'
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
        showToast(`Error deleting strategy: ${err.message}`, 'error');
    }
}

// Technical Chart View Across Timeframes
async function loadChartForSymbol(symbol, timeframe = null) {
    if (!symbol) return;
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

// Global function to jump directly to chart
window.openChartForSymbol = function(symbol, timeframe = null) {
    switchTab('chart');
    loadChartForSymbol(symbol, timeframe);
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

    // Backtest Analytics controls
    if (elements.btStrategySelect) {
        elements.btStrategySelect.addEventListener('change', (e) => {
            selectStrategy(Number(e.target.value), 'backtest');
        });
    }
    if (elements.btBtnRunScreener) {
        elements.btBtnRunScreener.addEventListener('click', () => runScreener(true));
    }
    if (elements.btBtnSaveStrategy) {
        elements.btBtnSaveStrategy.addEventListener('click', () => saveCurrentStrategy(true));
    }
    if (elements.btBtnDeleteStrategy) {
        elements.btBtnDeleteStrategy.addEventListener('click', () => deleteCurrentStrategy(true));
    }
    if (elements.btBtnExportExcel) {
        elements.btBtnExportExcel.addEventListener('click', () => exportResults('excel'));
    }
    if (elements.btCodeEditor) {
        elements.btCodeEditor.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                runScreener(true);
            }
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
}

// App Initialization
document.addEventListener('DOMContentLoaded', async () => {
    initTabs();
    initWatchlistUpload();
    initEventListeners();
    
    // Pre-cache all tickers in background for instant autosuggest
    loadAllSymbols();

    // Load initial data
    await loadStatus();
    await loadZerodhaStatus();
    await loadDates();
    await loadStrategies();
    
    // Ensure default view is Quant Screener tab
    switchTab('screener');
    
    // Load default chart in background
    loadChartForSymbol('RELIANCE', '1d');
});

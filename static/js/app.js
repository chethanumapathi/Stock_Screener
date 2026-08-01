document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const downloadDateInput = document.getElementById('downloadDate');
    const dateFallbackCheckbox = document.getElementById('dateFallback');
    const btnDownload = document.getElementById('btnDownload');
    const btnExport = document.getElementById('btnExport');
    const consoleLogs = document.getElementById('consoleLogs');
    const historyList = document.getElementById('historyList');
    const dbStatusText = document.getElementById('dbStatusText');
    const dbTotalRecords = document.getElementById('dbTotalRecords');
    const dbLastUpdated = document.getElementById('dbLastUpdated');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const statsSection = document.getElementById('statsSection');
    const gainersList = document.getElementById('gainersList');
    const losersList = document.getElementById('losersList');
    const volumeList = document.getElementById('volumeList');
    const stockSearch = document.getElementById('stockSearch');
    const stockList = document.getElementById('stockList');
    const chartContainer = document.getElementById('chartContainer');
    const chartMetrics = document.getElementById('chartMetrics');
    const metricSymbol = document.getElementById('metricSymbol');
    const metricClose = document.getElementById('metricClose');
    const metricChange = document.getElementById('metricChange');
    const metricVolume = document.getElementById('metricVolume');

    // Chart Legend Elements
    const chartLegend = document.getElementById('chartLegend');
    const legendDate = document.getElementById('legendDate');
    const legendOpen = document.getElementById('legendOpen');
    const legendHigh = document.getElementById('legendHigh');
    const legendLow = document.getElementById('legendLow');
    const legendClose = document.getElementById('legendClose');
    const legendVolume = document.getElementById('legendVolume');

    // State Variables & Chart Instances
    let activeDate = null;
    let chart = null;
    let candlestickSeries = null;
    let volumeSeries = null;
    let currentSymbol = null;
    let activeStockData = [];

    // Initialize Date Input to current local date
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    downloadDateInput.value = `${yyyy}-${mm}-${dd}`;
    downloadDateInput.max = `${yyyy}-${mm}-${dd}`; // Prevent picking future dates

    // Log a message to the UI console
    function logToConsole(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const entry = document.createElement('div');
        entry.className = `console-entry ${type}`;
        entry.textContent = `[${timestamp}] ${message}`;
        consoleLogs.appendChild(entry);
        consoleLogs.scrollTop = consoleLogs.scrollHeight;
    }

    // Format numbers
    function formatNumber(num) {
        if (num >= 10000000) {
            return (num / 10000000).toFixed(2) + ' Cr';
        } else if (num >= 100000) {
            return (num / 100000).toFixed(2) + ' L';
        }
        return Number(num).toLocaleString('en-IN');
    }

    // Update the floating legend content
    function updateLegend(time, ohlc, volume) {
        if (!chartLegend) return;
        
        let displayDate = '';
        if (time) {
            if (typeof time === 'string') {
                displayDate = time;
            } else if (time.year && time.month && time.day) {
                displayDate = `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
            }
        }
        
        legendDate.textContent = displayDate;
        legendOpen.textContent = ohlc.open.toFixed(2);
        legendHigh.textContent = ohlc.high.toFixed(2);
        legendLow.textContent = ohlc.low.toFixed(2);
        legendClose.textContent = ohlc.close.toFixed(2);
        legendVolume.textContent = volume ? formatNumber(volume) : '-';
        
        // Color coding open vs close
        const isBullish = ohlc.close >= ohlc.open;
        const color = isBullish ? '#10b981' : '#f43f5e';
        legendOpen.style.color = color;
        legendHigh.style.color = color;
        legendLow.style.color = color;
        legendClose.style.color = color;
    }

    // Reset legend to display the most recent data point
    function showLastBarData() {
        if (activeStockData.length === 0) return;
        const last = activeStockData[activeStockData.length - 1];
        updateLegend(last.time, last, last.volume);
    }

    // Initialize TradingView Candlestick Chart
    function initChart() {
        if (!chartContainer) return;
        
        // Remove empty state only (preserves chartLegend element)
        const emptyState = document.getElementById('emptyChartState');
        if (emptyState) emptyState.remove();

        const width = chartContainer.clientWidth;
        const height = chartContainer.clientHeight || 450;

        try {
            chart = LightweightCharts.createChart(chartContainer, {
                width: width,
                height: height,
                layout: {
                    background: { type: 'solid', color: '#000000' },
                    textColor: '#94a3b8',
                    fontFamily: "'Inter', sans-serif",
                },
                grid: {
                    vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
                    horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: {
                        color: 'rgba(99, 102, 241, 0.5)',
                        width: 1,
                        style: 3,
                    },
                    horzLine: {
                        color: 'rgba(99, 102, 241, 0.5)',
                        width: 1,
                        style: 3,
                    },
                },
                rightPriceScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    visible: true,
                },
                timeScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    timeVisible: true,
                    secondsVisible: false,
                },
            });
        } catch (e) {
            console.error("Failed to create chart:", e);
            logToConsole(`Failed to initialize chart: ${e.message}`, 'error');
            return;
        }

        // Version-agnostic candlestick series creation (supports v4 and v5)
        const candlestickOptions = {
            upColor: '#10b981',      // Bullish Green
            downColor: '#f43f5e',    // Bearish Red
            borderUpColor: '#10b981',
            borderDownColor: '#f43f5e',
            wickUpColor: '#10b981',
            wickDownColor: '#f43f5e',
        };

        if (typeof chart.addCandlestickSeries === 'function') {
            candlestickSeries = chart.addCandlestickSeries(candlestickOptions);
        } else if (typeof chart.addSeries === 'function') {
            candlestickSeries = chart.addSeries(LightweightCharts.CandlestickSeries, candlestickOptions);
        } else {
            console.error("Could not find a method to add Candlestick series to chart.");
        }

        // Version-agnostic volume overlay series creation (supports v4 and v5)
        const volumeOptions = {
            color: '#3b82f6',
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '', // Overlay main pane
        };

        if (typeof chart.addHistogramSeries === 'function') {
            volumeSeries = chart.addHistogramSeries(volumeOptions);
        } else if (typeof chart.addSeries === 'function') {
            volumeSeries = chart.addSeries(LightweightCharts.HistogramSeries, volumeOptions);
        } else {
            console.error("Could not find a method to add Histogram series to chart.");
        }

        // Set Volume margins
        if (volumeSeries) {
            volumeSeries.priceScale().applyOptions({
                scaleMargins: {
                    top: 0.75, // volume at bottom 25% of pane
                    bottom: 0,
                },
            });
        }

        // Dynamic crosshair movement legend updates
        chart.subscribeCrosshairMove(param => {
            if (!param.point || !param.time || param.point.x < 0 || param.point.x > chartContainer.clientWidth || param.point.y < 0 || param.point.y > chartContainer.clientHeight) {
                showLastBarData();
                return;
            }
            
            const ohlc = param.seriesData.get(candlestickSeries);
            const volumeData = param.seriesData.get(volumeSeries);
            
            if (ohlc) {
                updateLegend(param.time, ohlc, volumeData ? volumeData.value : null);
            }
        });

        // Make responsive to resize
        window.addEventListener('resize', () => {
            if (chart && chartContainer) {
                chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
            }
        });
    }

    // Load available stock symbols for search lists
    async function loadStockSymbols() {
        try {
            const response = await fetch('/api/stocks');
            const result = await response.json();
            if (result.status === 'success') {
                stockList.innerHTML = '';
                result.symbols.forEach(symbol => {
                    const option = document.createElement('option');
                    option.value = symbol;
                    stockList.appendChild(option);
                });
                logToConsole(`Loaded ${result.symbols.length} unique symbols for charting.`, 'info');
                
                // Select a default stock (RELIANCE or the first one)
                if (result.symbols.length > 0) {
                    const defaultStock = result.symbols.includes('RELIANCE') ? 'RELIANCE' : result.symbols[0];
                    loadStockChart(defaultStock);
                }
            }
        } catch (error) {
            logToConsole(`Error loading symbols: ${error.message}`, 'error');
        }
    }

    // Load historical stock data onto the chart
    async function loadStockChart(symbol) {
        if (!symbol) return;
        symbol = symbol.trim().toUpperCase();
        
        logToConsole(`Fetching chart data for ${symbol}...`);
        
        try {
            const response = await fetch(`/api/stock/${symbol}`);
            const result = await response.json();
            
            if (result.status === 'success' && result.data.length > 0) {
                currentSymbol = symbol;
                stockSearch.value = symbol;
                
                // Store active stock data for legend reference
                activeStockData = result.data;
                
                // Format data for chart
                const ohlcData = result.data.map(d => ({
                    time: d.time,
                    open: d.open,
                    high: d.high,
                    low: d.low,
                    close: d.close
                }));
                
                const volData = result.data.map(d => {
                    const isBullish = d.close >= d.open;
                    return {
                        time: d.time,
                        value: d.volume,
                        color: isBullish ? 'rgba(16, 185, 129, 0.45)' : 'rgba(244, 63, 94, 0.45)'
                    };
                });
                
                // Render
                candlestickSeries.setData(ohlcData);
                volumeSeries.setData(volData);
                
                // Adjust scale
                chart.timeScale().fitContent();
                
                // Populate Metric Bar
                const lastRow = result.data[result.data.length - 1];
                const prevClose = result.data.length > 1 ? result.data[result.data.length - 2].close : lastRow.open;
                const changePct = ((lastRow.close - prevClose) / prevClose * 100).toFixed(2);
                const changeSymbol = changePct >= 0 ? '+' : '';
                
                metricSymbol.textContent = symbol;
                metricClose.textContent = lastRow.close.toFixed(2);
                metricChange.textContent = `${changeSymbol}${changePct}%`;
                metricChange.style.color = changePct >= 0 ? 'var(--success)' : 'var(--danger)';
                metricVolume.textContent = formatNumber(lastRow.volume);
                
                chartMetrics.style.display = 'flex';
                
                // Initialize floating legend
                if (chartLegend) chartLegend.style.display = 'flex';
                showLastBarData();
                
                logToConsole(`Rendered chart for ${symbol} with ${ohlcData.length} records.`, 'info');
            } else {
                logToConsole(`Error: ${result.message || 'No chart data available'}`, 'error');
            }
        } catch (error) {
            logToConsole(`Error drawing chart: ${error.message}`, 'error');
        }
    }

    // Refresh database statistics and history list
    async function loadDashboardStats(selectFirstDate = false) {
        try {
            const response = await fetch('/api/history');
            const data = await response.json();

            // Update stats indicators
            if (data.total_records > 0) {
                dbStatusText.textContent = 'Active';
                dbStatusText.style.color = '#10b981';
                dbTotalRecords.textContent = data.total_records.toLocaleString('en-IN');
                dbLastUpdated.textContent = data.last_updated;
            } else {
                dbStatusText.textContent = 'Empty';
                dbStatusText.style.color = 'var(--text-muted)';
                dbTotalRecords.textContent = '0';
                dbLastUpdated.textContent = 'Never';
            }

            // Update history list
            historyList.innerHTML = '';
            if (data.downloaded_dates && data.downloaded_dates.length > 0) {
                data.downloaded_dates.forEach((dateStr, index) => {
                    const item = document.createElement('div');
                    item.className = 'history-item';
                    if (activeDate === dateStr) {
                        item.classList.add('active');
                    }
                    
                    // Format date for show
                    const dateObj = new Date(dateStr);
                    const formattedDisplayDate = dateObj.toLocaleDateString('en-IN', {
                        day: '2-digit',
                        month: 'short',
                        year: 'numeric'
                    });

                    item.innerHTML = `
                        <span class="history-date">${formattedDisplayDate}</span>
                        <span class="history-action">View Data &rarr;</span>
                    `;
                    item.addEventListener('click', () => {
                        // Mark active class
                        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
                        item.classList.add('active');
                        viewDateData(dateStr);
                    });
                    historyList.appendChild(item);
                });

                // Auto-select first date if requested and not currently previewing anything
                if (selectFirstDate && data.downloaded_dates.length > 0) {
                    activeDate = data.downloaded_dates[0];
                    const firstItem = historyList.querySelector('.history-item');
                    if (firstItem) firstItem.classList.add('active');
                    viewDateData(activeDate);
                }
            } else {
                historyList.innerHTML = `
                    <div class="empty-state" style="padding: 1rem 0;">
                        <p style="font-size: 0.8rem; color: var(--text-muted);">No downloads recorded yet.</p>
                    </div>
                `;
            }
        } catch (error) {
            logToConsole(`Error loading history: ${error.message}`, 'error');
        }
    }

    // View specific date data & update daily stats cards
    async function viewDateData(dateStr) {
        activeDate = dateStr;
        logToConsole(`Loading daily stats for ${dateStr}...`);
        
        try {
            const response = await fetch(`/api/view_data?date=${dateStr}`);
            const result = await response.json();
            
            if (result.status === 'success') {
                // Populate Stats Cards
                if (result.stats) {
                    populateStatsCards(result.stats);
                    statsSection.style.display = 'grid';
                } else {
                    statsSection.style.display = 'none';
                }
                
                logToConsole(`Successfully loaded stats for ${dateStr}.`, 'info');
            } else {
                logToConsole(`Error: ${result.message}`, 'error');
                statsSection.style.display = 'none';
            }
        } catch (error) {
            logToConsole(`Error fetching daily stats: ${error.message}`, 'error');
        }
    }

    // Populate Top Gainers, Losers, and Volume cards & add click events to load chart
    function populateStatsCards(stats) {
        // Gainers
        gainersList.innerHTML = '';
        if (stats.top_gainers && stats.top_gainers.length > 0) {
            stats.top_gainers.forEach(g => {
                const row = document.createElement('div');
                row.className = 'ticker-row';
                row.style.cursor = 'pointer';
                row.innerHTML = `
                    <span class="ticker-symbol">${g.Symbol}</span>
                    <div style="text-align:right;">
                        <span class="ticker-value">${g.Close.toFixed(2)}</span>
                        <span class="ticker-change up">+${g.Pct_Change}%</span>
                    </div>
                `;
                row.addEventListener('click', () => loadStockChart(g.Symbol));
                gainersList.appendChild(row);
            });
        } else {
            gainersList.innerHTML = '<div style="color:var(--text-muted); font-size:0.8rem; text-align:center; padding:1rem 0;">No stats available</div>';
        }

        // Losers
        losersList.innerHTML = '';
        if (stats.top_losers && stats.top_losers.length > 0) {
            stats.top_losers.forEach(l => {
                const row = document.createElement('div');
                row.className = 'ticker-row';
                row.style.cursor = 'pointer';
                row.innerHTML = `
                    <span class="ticker-symbol">${l.Symbol}</span>
                    <div style="text-align:right;">
                        <span class="ticker-value">${l.Close.toFixed(2)}</span>
                        <span class="ticker-change down">${l.Pct_Change}%</span>
                    </div>
                `;
                row.addEventListener('click', () => loadStockChart(l.Symbol));
                losersList.appendChild(row);
            });
        } else {
            losersList.innerHTML = '<div style="color:var(--text-muted); font-size:0.8rem; text-align:center; padding:1rem 0;">No stats available</div>';
        }

        // Volumes
        volumeList.innerHTML = '';
        if (stats.high_volume && stats.high_volume.length > 0) {
            stats.high_volume.forEach(v => {
                const row = document.createElement('div');
                row.className = 'ticker-row';
                row.style.cursor = 'pointer';
                row.innerHTML = `
                    <span class="ticker-symbol">${v.Symbol}</span>
                    <div style="text-align:right; display:flex; flex-direction:column; align-items:flex-end;">
                        <span class="ticker-value" style="font-weight:600;">${v.Close.toFixed(2)}</span>
                        <span class="ticker-vol">Vol: ${formatNumber(v.Volume)}</span>
                    </div>
                `;
                row.addEventListener('click', () => loadStockChart(v.Symbol));
                volumeList.appendChild(row);
            });
        } else {
            volumeList.innerHTML = '<div style="color:var(--text-muted); font-size:0.8rem; text-align:center; padding:1rem 0;">No stats available</div>';
        }
    }

    // Trigger Download API call
    btnDownload.addEventListener('click', async () => {
        const dateVal = downloadDateInput.value;
        if (!dateVal) {
            logToConsole('Please select a date to download.', 'error');
            return;
        }

        logToConsole(`Initiating download request for date: ${dateVal}...`);
        loadingOverlay.style.display = 'flex';
        
        try {
            const response = await fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    date: dateVal,
                    fallback: dateFallbackCheckbox.checked
                })
            });

            const result = await response.json();
            loadingOverlay.style.display = 'none';

            if (response.ok && result.status === 'success') {
                logToConsole(`SUCCESS! Downloaded Bhavcopy for: ${result.date}`, 'info');
                logToConsole(`Processed ${result.records_downloaded.toLocaleString('en-IN')} stocks.`, 'info');
                if (result.backtracked_days > 0) {
                    logToConsole(`Note: Requested date was fallback. Automatically backtracked ${result.backtracked_days} day(s) to hit the last open market.`, 'info');
                }
                logToConsole(`Total database size now: ${result.total_database_records.toLocaleString('en-IN')} records.`, 'info');
                
                // Select and load the newly downloaded date
                activeDate = result.date;
                await loadDashboardStats(false);
                await viewDateData(activeDate);
            } else {
                logToConsole(`FAILED: ${result.message || 'Unknown backend error'}`, 'error');
                alert(`Download Failed: ${result.message}`);
            }
        } catch (error) {
            loadingOverlay.style.display = 'none';
            logToConsole(`Network or Server error: ${error.message}`, 'error');
            alert(`Error: Could not reach the server.`);
        }
    });

    // Trigger Consolidated Export
    btnExport.addEventListener('click', () => {
        logToConsole('Requesting consolidated CSV file export...');
        window.location.href = '/api/export';
    });

    // Chart symbol selection event listeners
    stockSearch.addEventListener('change', () => {
        loadStockChart(stockSearch.value);
    });
    stockSearch.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            loadStockChart(stockSearch.value);
        }
    });

    // --- Stock Screener Frontend Bindings & Logic ---
    const screenerSegment = document.getElementById('screenerSegment');
    const watchlistUploadContainer = document.getElementById('watchlistUploadContainer');
    const watchlistFile = document.getElementById('watchlistFile');
    const watchlistStatus = document.getElementById('watchlistStatus');
    const btnRunScreener = document.getElementById('btnRunScreener');
    const screenerCode = document.getElementById('screenerCode');
    const screenerResultsContainer = document.getElementById('screenerResultsContainer');
    const screenerResultsCount = document.getElementById('screenerResultsCount');
    const screenerTableHeader = document.getElementById('screenerTableHeader');
    const screenerTableBody = document.getElementById('screenerTableBody');
    const emptyScreenerState = document.getElementById('emptyScreenerState');

    let watchlistSymbols = null;

    // --- Stock Screener Backtesting State ---
    let activeScreenerResults = null;
    let screenerDates = [];
    let activeScreenerDateIndex = -1;
    let backtestChart = null;

    // Show/Hide Watchlist Upload Box
    screenerSegment.addEventListener('change', () => {
        if (screenerSegment.value === 'watchlist') {
            watchlistUploadContainer.style.display = 'flex';
        } else {
            watchlistUploadContainer.style.display = 'none';
        }
    });

    // Handle Watchlist File Upload and Parsing
    watchlistFile.addEventListener('change', async () => {
        const file = watchlistFile.files[0];
        if (!file) return;

        watchlistStatus.textContent = 'Parsing...';
        watchlistStatus.style.color = 'var(--text-muted)';
        logToConsole(`Uploading watchlist file: ${file.name}...`);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/screener/parse_watchlist', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                watchlistSymbols = result.symbols;
                watchlistStatus.textContent = `Parsed ${result.symbols.length} symbols successfully.`;
                watchlistStatus.style.color = '#10b981';
                logToConsole(`Loaded custom watchlist containing ${result.symbols.length} symbols.`, 'info');
            } else {
                watchlistSymbols = null;
                watchlistStatus.textContent = `Error: ${result.message || 'Parsing failed'}`;
                watchlistStatus.style.color = '#f43f5e';
                logToConsole(`Watchlist error: ${result.message}`, 'error');
            }
        } catch (error) {
            watchlistSymbols = null;
            watchlistStatus.textContent = 'Network error.';
            watchlistStatus.style.color = '#f43f5e';
            logToConsole(`Watchlist upload failed: ${error.message}`, 'error');
        }
    });

    // Render Backtest Distribution Bar Chart
    function renderBacktestChart(historicalResults) {
        const dates = Object.keys(historicalResults).sort(); // Sort dates chronologically
        const counts = dates.map(dt => historicalResults[dt].length);
        
        screenerDates = dates;
        activeScreenerResults = historicalResults;
        
        // Show chart panel
        document.getElementById('screenerChartPanel').style.display = 'flex';
        
        if (backtestChart) {
            backtestChart.destroy();
        }
        
        const ctx = document.getElementById('backtestBarChart').getContext('2d');
        backtestChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: dates.map(d => {
                    const parts = d.split('-');
                    if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`; // DD-MM-YYYY
                    return d;
                }),
                datasets: [{
                    label: 'Matched Stocks',
                    data: counts,
                    backgroundColor: 'rgba(99, 102, 241, 0.65)',
                    borderColor: '#6366f1',
                    borderWidth: 1,
                    hoverBackgroundColor: 'rgba(167, 139, 250, 0.95)',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(15, 22, 42, 0.95)',
                        titleColor: '#fff',
                        bodyColor: '#a78bfa',
                        borderColor: 'rgba(255,255,255,0.08)',
                        borderWidth: 1,
                        displayColors: false,
                        callbacks: {
                            title: (tooltipItems) => {
                                const idx = tooltipItems[0].dataIndex;
                                const originalDate = dates[idx];
                                const parts = originalDate.split('-');
                                return `Date: ${parts[2]}-${parts[1]}-${parts[0]}`;
                            },
                            label: (tooltipItem) => {
                                return `Matched: ${tooltipItem.formattedValue} stocks`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.4)',
                            font: { size: 9 },
                            maxRotation: 45,
                            minRotation: 45
                        }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.4)',
                            font: { size: 9 },
                            stepSize: 1
                        }
                    }
                },
                onClick: (event, elements) => {
                    if (elements && elements.length > 0) {
                        const elementIndex = elements[0].index;
                        const clickedDate = dates[elementIndex];
                        displayScreenerDateResults(clickedDate);
                    }
                }
            }
        });
    }

    // Display Screener Results for a specific Date
    function displayScreenerDateResults(dateStr) {
        if (!activeScreenerResults || !activeScreenerResults[dateStr]) return;

        const records = activeScreenerResults[dateStr];
        activeScreenerDateIndex = screenerDates.indexOf(dateStr);

        // Update active displays and UI controls
        document.getElementById('screenerNavigationControls').style.display = 'flex';
        
        const parts = dateStr.split('-');
        const formattedDate = parts.length === 3 ? `${parts[2]}-${parts[1]}-${parts[0]}` : dateStr;
        
        document.getElementById('screenerActiveDateDisplay').textContent = formattedDate;
        document.getElementById('screenerResultsTitle').textContent = `Matches on`;
        document.getElementById('screenerResultsCount').textContent = `Found ${records.length} matches`;

        // Update button states
        document.getElementById('btnPrevScreenerDate').disabled = (activeScreenerDateIndex <= 0);
        document.getElementById('btnNextScreenerDate').disabled = (activeScreenerDateIndex >= screenerDates.length - 1);
        
        // Update opacity/highlight style of active bar in Chart.js
        if (backtestChart) {
            const bgColors = screenerDates.map(dt => dt === dateStr ? 'rgba(167, 139, 250, 0.95)' : 'rgba(99, 102, 241, 0.5)');
            backtestChart.data.datasets[0].backgroundColor = bgColors;
            backtestChart.update();
        }

        // Reconstruct Table Headers
        screenerTableHeader.innerHTML = `
            <th style="padding: 0.75rem 1rem; color: var(--text-secondary); font-weight: 600;">Symbol</th>
            <th style="padding: 0.75rem 1rem; color: var(--text-secondary); font-weight: 600; text-align: right;">Close</th>
            <th style="padding: 0.75rem 1rem; color: var(--text-secondary); font-weight: 600; text-align: right;">Daily Change</th>
            <th style="padding: 0.75rem 1rem; color: var(--text-secondary); font-weight: 600; text-align: right;">Volume</th>
        `;

        const customKeys = new Set();
        records.forEach(item => {
            if (item.custom_data) {
                Object.keys(item.custom_data).forEach(k => customKeys.add(k));
            }
        });

        customKeys.forEach(k => {
            const th = document.createElement('th');
            th.style.padding = '0.75rem 1rem';
            th.style.color = 'var(--text-secondary)';
            th.style.fontWeight = '600';
            th.style.textAlign = 'right';
            th.textContent = k;
            screenerTableHeader.appendChild(th);
        });

        // Populate Table Rows
        screenerTableBody.innerHTML = '';
        records.forEach(row => {
            const tr = document.createElement('tr');
            tr.className = 'screener-result-row';
            tr.style.borderBottom = '1px solid rgba(255, 255, 255, 0.03)';
            tr.style.cursor = 'pointer';

            const pctChange = row.Pct_Change;
            const changeClass = pctChange >= 0 ? 'up' : 'down';
            const changeSymbol = pctChange >= 0 ? '+' : '';

            let cellsHtml = `
                <td class="ticker-symbol" style="padding: 0.75rem 1rem; font-weight: 600;">${row.Symbol}</td>
                <td style="padding: 0.75rem 1rem; text-align: right; color: var(--text-primary); font-family: monospace;">${row.Close.toFixed(2)}</td>
                <td style="padding: 0.75rem 1rem; text-align: right; font-family: monospace;" class="ticker-change ${changeClass}">${changeSymbol}${pctChange}%</td>
                <td style="padding: 0.75rem 1rem; text-align: right; color: var(--text-secondary); font-family: monospace;">${formatNumber(row.Volume)}</td>
            `;

            customKeys.forEach(k => {
                const val = row.custom_data && row.custom_data[k] !== undefined ? row.custom_data[k] : '-';
                cellsHtml += `<td style="padding: 0.75rem 1rem; text-align: right; color: #a78bfa; font-family: monospace;">${val}</td>`;
            });

            tr.innerHTML = cellsHtml;

            // Click to load chart
            tr.addEventListener('click', () => {
                loadStockChart(row.Symbol);
                document.getElementById('chartContainer').scrollIntoView({ behavior: 'smooth' });
            });

            screenerTableBody.appendChild(tr);
        });
    }

    // Navigation Button Actions
    document.getElementById('btnPrevScreenerDate').addEventListener('click', () => {
        if (activeScreenerDateIndex > 0) {
            displayScreenerDateResults(screenerDates[activeScreenerDateIndex - 1]);
        }
    });

    document.getElementById('btnNextScreenerDate').addEventListener('click', () => {
        if (activeScreenerDateIndex < screenerDates.length - 1) {
            displayScreenerDateResults(screenerDates[activeScreenerDateIndex + 1]);
        }
    });

    document.getElementById('btnResetScreenerDate').addEventListener('click', () => {
        if (screenerDates.length > 0) {
            displayScreenerDateResults(screenerDates[screenerDates.length - 1]);
        }
    });

    // Run custom script screener
    btnRunScreener.addEventListener('click', async () => {
        if (screenerSegment.value === 'watchlist' && (!watchlistSymbols || watchlistSymbols.length === 0)) {
            alert('Please upload a valid Watchlist file (Excel/CSV) first.');
            return;
        }

        const originalBtnHtml = btnRunScreener.innerHTML;
        btnRunScreener.disabled = true;
        btnRunScreener.innerHTML = `
            <svg class="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation: spin 1s linear infinite; margin-right: 4px;"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle><path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
            Screening...
        `;
        logToConsole(`Running stock screener on universe: ${screenerSegment.value}...`);

        try {
            const response = await fetch('/api/screener/run', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    code: screenerCode.value,
                    segment: screenerSegment.value,
                    watchlist: watchlistSymbols
                })
            });
            const result = await response.json();

            btnRunScreener.disabled = false;
            btnRunScreener.innerHTML = originalBtnHtml;

            if (response.ok && result.status === 'success') {
                emptyScreenerState.style.display = 'none';
                
                const dates = Object.keys(result.historical_results).sort();
                if (dates.length === 0) {
                    screenerResultsContainer.style.display = 'flex';
                    document.getElementById('screenerChartPanel').style.display = 'none';
                    document.getElementById('screenerNavigationControls').style.display = 'none';
                    document.getElementById('screenerResultsTitle').textContent = `Screener Results`;
                    document.getElementById('screenerResultsCount').textContent = `Found 0 matches`;
                    screenerTableBody.innerHTML = `
                        <tr>
                            <td colspan="4" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">No stocks matched your screen conditions.</td>
                        </tr>
                    `;
                    logToConsole('Screening complete. Found 0 matches.', 'info');
                } else {
                    screenerResultsContainer.style.display = 'flex';
                    // Render Chart
                    renderBacktestChart(result.historical_results);
                    // Select and display results for the latest date (last element)
                    const latestDate = dates[dates.length - 1];
                    displayScreenerDateResults(latestDate);
                    
                    const totalMatchesCount = Object.values(result.historical_results).reduce((acc, list) => acc + list.length, 0);
                    logToConsole(`Backtest complete. Found ${totalMatchesCount} matches across ${dates.length} trading sessions.`, 'info');
                }
            } else {
                logToConsole(`Screening error: ${result.message}`, 'error');
                alert(`Screening failed: ${result.message}`);
            }
        } catch (error) {
            btnRunScreener.disabled = false;
            btnRunScreener.innerHTML = originalBtnHtml;
            logToConsole(`Screening execution failed: ${error.message}`, 'error');
            alert(`Error running screener: ${error.message}`);
        }
    });

    // --- Help Modal Triggers ---
    const btnOpenScreenerHelp = document.getElementById('btnOpenScreenerHelp');
    const btnCloseScreenerHelp = document.getElementById('btnCloseScreenerHelp');
    const screenerHelpModal = document.getElementById('screenerHelpModal');

    btnOpenScreenerHelp.addEventListener('click', () => {
        screenerHelpModal.style.display = 'flex';
    });

    btnCloseScreenerHelp.addEventListener('click', () => {
        screenerHelpModal.style.display = 'none';
    });

    // Close modal on background click
    screenerHelpModal.addEventListener('click', (e) => {
        if (e.target === screenerHelpModal) {
            screenerHelpModal.style.display = 'none';
        }
    });

    // Initialize Dashboard & Chart
    initChart();
    loadStockSymbols();
    loadDashboardStats(true);
});

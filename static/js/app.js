document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const downloadFromDateInput = document.getElementById('downloadFromDate');
    const downloadToDateInput = document.getElementById('downloadToDate');
    const dateFallbackWrapper = document.getElementById('dateFallbackWrapper');
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
    let downloadedDatesList = []; // Kept up-to-date with downloaded dates
    let databaseDatesList = []; // Kept up-to-date with database dates (actually consolidated)

    // Drawing & Indicators State
    let activeTool = 'cursor'; // 'cursor', 'trendline', 'measure'
    let trendlines = [];
    let measurement = null;
    let activeMAs = []; // Array of { id, type, length, color, series }
    let rsiChart = null;
    let rsiSeries = null;
    let pivotLines = []; // Array of price line instances
    
    // Drawing mouse tracking state
    let isDrawing = false;
    let drawStart = null;
    let drawCurrent = null;
    let isMovingCrosshair = false;

    // Initialize Date Inputs
    const today = new Date();
    const formatISODate = (d) => {
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}`;
    };

    // Default From Date to 7 days ago, To Date to today
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(today.getDate() - 7);

    downloadFromDateInput.value = formatISODate(sevenDaysAgo);
    downloadFromDateInput.max = formatISODate(today);
    downloadToDateInput.value = formatISODate(today);
    downloadToDateInput.max = formatISODate(today);

    // Show/hide fallback checkbox based on whether it is single date
    const updateFallbackVisibility = () => {
        if (downloadFromDateInput.value === downloadToDateInput.value) {
            dateFallbackWrapper.style.display = 'block';
        } else {
            dateFallbackWrapper.style.display = 'none';
        }
    };
    downloadFromDateInput.addEventListener('change', updateFallbackVisibility);
    downloadToDateInput.addEventListener('change', updateFallbackVisibility);
    updateFallbackVisibility();

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

    // --- Helper Math/Calculation Functions ---
    function calculateSMA(data, period) {
        let sma = [];
        for (let i = 0; i < data.length; i++) {
            if (i < period - 1) {
                sma.push({ time: data[i].time, value: NaN });
            } else {
                let sum = 0;
                for (let j = 0; j < period; j++) {
                    sum += data[i - j].close;
                }
                sma.push({ time: data[i].time, value: sum / period });
            }
        }
        return sma.filter(d => !isNaN(d.value));
    }

    function calculateEMA(data, period) {
        let ema = [];
        if (data.length === 0) return ema;
        let k = 2 / (period + 1);
        let prevEma = 0;
        
        let initialSum = 0;
        const initCount = Math.min(period, data.length);
        for (let i = 0; i < initCount; i++) {
            initialSum += data[i].close;
        }
        prevEma = initialSum / initCount;

        for (let i = 0; i < data.length; i++) {
            if (i < period - 1) {
                ema.push({ time: data[i].time, value: NaN });
            } else if (i === period - 1) {
                ema.push({ time: data[i].time, value: prevEma });
            } else {
                let currentEma = data[i].close * k + prevEma * (1 - k);
                ema.push({ time: data[i].time, value: currentEma });
                prevEma = currentEma;
            }
        }
        return ema.filter(d => !isNaN(d.value));
    }

    function calculateRSI(data, period) {
        if (data.length <= period) return [];
        let rsiData = [];
        let gains = [];
        let losses = [];
        
        for (let i = 1; i < data.length; i++) {
            let diff = data[i].close - data[i-1].close;
            gains.push(diff > 0 ? diff : 0);
            losses.push(diff < 0 ? -diff : 0);
        }
        
        let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
        let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
        
        let rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        rsiData.push({ time: data[period].time, value: 100 - (100 / (1 + rs)) });
        
        for (let i = period; i < gains.length; i++) {
            avgGain = (avgGain * (period - 1) + gains[i]) / period;
            avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
            rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
            rsiData.push({ time: data[i+1].time, value: 100 - (100 / (1 + rs)) });
        }
        return rsiData;
    }

    function calculatePivots(data) {
        if (data.length < 2) return null;
        const prevDay = data[data.length - 2];
        const high = prevDay.high;
        const low = prevDay.low;
        const close = prevDay.close;
        
        const pp = (high + low + close) / 3;
        const r1 = 2 * pp - low;
        const s1 = 2 * pp - high;
        const r2 = pp + (high - low);
        const s2 = pp - (high - low);
        const r3 = high + 2 * (pp - low);
        const s3 = low - 2 * (high - pp);
        return { pp, r1, s1, r2, s2, r3, s3 };
    }

    function hexToRgba(hex, alpha = 1) {
        hex = hex.replace('#', '');
        let r = parseInt(hex.substring(0, 2), 16);
        let g = parseInt(hex.substring(2, 4), 16);
        let b = parseInt(hex.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    function roundRect(ctx, x, y, width, height, radius = 5, fill = false, stroke = true) {
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        ctx.lineTo(x + width, y + height - radius);
        ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
        ctx.lineTo(x + radius, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
        ctx.lineTo(x, y + radius);
        ctx.quadraticCurveTo(x, y, x + radius, y);
        ctx.closePath();
        if (fill) ctx.fill();
        if (stroke) ctx.stroke();
    }

    // --- Overlay drawing coordinates conversion and rendering ---
    function chartToPixel(coord) {
        if (!coord || !chart || !candlestickSeries) return null;
        const x = chart.timeScale().timeToCoordinate(coord.time);
        const y = candlestickSeries.priceToCoordinate(coord.price);
        return { x, y };
    }

    function drawMeasurementBox(ctx, start, end, isTemp) {
        const startPos = chartToPixel(start);
        const endPos = chartToPixel(end);
        if (!startPos || !endPos || startPos.x === null || startPos.y === null || endPos.x === null || endPos.y === null) return;
        
        const x = Math.min(startPos.x, endPos.x);
        const y = Math.min(startPos.y, endPos.y);
        const w = Math.abs(startPos.x - endPos.x);
        const h = Math.abs(startPos.y - endPos.y);
        
        const color = (end.price >= start.price) ? '16, 185, 129' : '244, 63, 94';
        ctx.fillStyle = `rgba(${color}, ${isTemp ? 0.12 : 0.08})`;
        ctx.fillRect(x, y, w, h);
        
        ctx.strokeStyle = `rgba(${color}, ${isTemp ? 0.6 : 0.4})`;
        ctx.lineWidth = 1;
        ctx.strokeRect(x, y, w, h);
        
        const priceDiff = end.price - start.price;
        const pctDiff = (priceDiff / start.price * 100).toFixed(2);
        
        let bars = 0;
        if (activeStockData.length > 0) {
            const startIndex = activeStockData.findIndex(d => d.time === start.time);
            const endIndex = activeStockData.findIndex(d => d.time === end.time);
            if (startIndex !== -1 && endIndex !== -1) {
                bars = Math.abs(endIndex - startIndex) + 1;
            }
        }
        
        const directionSign = priceDiff >= 0 ? '+' : '';
        const text = `${directionSign}${priceDiff.toFixed(2)} (${directionSign}${pctDiff}%), ${bars} bars`;
        
        ctx.font = 'bold 11px Inter, sans-serif';
        const textWidth = ctx.measureText(text).width;
        const padX = 8;
        const padY = 5;
        
        const lblX = endPos.x - textWidth / 2;
        const lblY = endPos.y + (priceDiff >= 0 ? -25 : 10);
        
        ctx.fillStyle = '#0f172a';
        ctx.strokeStyle = `rgba(${color}, 0.8)`;
        ctx.lineWidth = 1.5;
        roundRect(ctx, lblX - padX, lblY - padY, textWidth + padX * 2, 16 + padY * 2, 4, true, true);
        
        ctx.fillStyle = (priceDiff >= 0) ? '#10b981' : '#f43f5e';
        ctx.fillText(text, lblX, lblY + 12);
    }

    function redrawCanvas() {
        const drawingCanvas = document.getElementById('drawingCanvas');
        if (!drawingCanvas) return;
        const ctx = drawingCanvas.getContext('2d');
        ctx.clearRect(0, 0, drawingCanvas.width, drawingCanvas.height);
        
        // 1. Draw Pivot Points (both lines and shading segmented monthly)
        const togglePivots = document.getElementById('togglePivots');
        if (togglePivots && togglePivots.checked && activeStockData.length >= 2 && candlestickSeries) {
            // Group by month
            const monthlyData = {};
            activeStockData.forEach(d => {
                let key = null;
                if (typeof d.time === 'string') {
                    key = d.time.substring(0, 7); // 'YYYY-MM'
                } else if (d.time && d.time.year && d.time.month) {
                    key = `${d.time.year}-${String(d.time.month).padStart(2, '0')}`;
                }
                if (!key) return;
                if (!monthlyData[key]) monthlyData[key] = [];
                monthlyData[key].push(d);
            });

            const months = Object.keys(monthlyData).sort();
            const monthlyOhlc = {};
            months.forEach(key => {
                const days = monthlyData[key];
                const high = Math.max(...days.map(d => d.high));
                const low = Math.min(...days.map(d => d.low));
                const close = days[days.length - 1].close;
                monthlyOhlc[key] = { high, low, close };
            });

            const resColor = document.getElementById('pivotResColor').value;
            const supColor = document.getElementById('pivotSupColor').value;
            const pivotsShading = document.getElementById('pivotsShading').checked;

            // Draw for each month (starting from index 1 since index 0 has no prior month to calculate from)
            for (let i = 1; i < months.length; i++) {
                const currentMonth = months[i];
                const prevMonth = months[i - 1];
                const ohlc = monthlyOhlc[prevMonth];
                const days = monthlyData[currentMonth];
                if (!days || days.length === 0) continue;

                // Monthly pivot levels
                const pp = (ohlc.high + ohlc.low + ohlc.close) / 3;
                const r1 = 2 * pp - ohlc.low;
                const s1 = 2 * pp - ohlc.high;
                const r2 = pp + (ohlc.high - ohlc.low);
                const s2 = pp - (ohlc.high - ohlc.low);
                const r3 = ohlc.high + 2 * (pp - ohlc.low);
                const s3 = ohlc.low - 2 * (ohlc.high - pp);

                // Coordinates
                const firstDay = days[0];
                const lastDay = days[days.length - 1];

                let xStart = chart.timeScale().timeToCoordinate(firstDay.time);
                let xEnd = chart.timeScale().timeToCoordinate(lastDay.time);

                // Extend xEnd to edge of canvas if it's the current month
                if (i === months.length - 1) {
                    xEnd = drawingCanvas.width;
                }

                if (xStart === null || xEnd === null) continue;

                // Y Coordinates
                const yPP = candlestickSeries.priceToCoordinate(pp);
                const yR1 = candlestickSeries.priceToCoordinate(r1);
                const yR2 = candlestickSeries.priceToCoordinate(r2);
                const yR3 = candlestickSeries.priceToCoordinate(r3);
                const yS1 = candlestickSeries.priceToCoordinate(s1);
                const yS2 = candlestickSeries.priceToCoordinate(s2);
                const yS3 = candlestickSeries.priceToCoordinate(s3);

                // Draw shading
                if (pivotsShading) {
                    const w = xEnd - xStart;
                    
                    // Center zone: R1 to S1 (Neutral dark gray)
                    if (yR1 !== null && yS1 !== null) {
                        ctx.fillStyle = 'rgba(255, 255, 255, 0.03)';
                        ctx.fillRect(xStart, Math.min(yR1, yS1), w, Math.abs(yR1 - yS1));
                    }
                    
                    // Intermediate zones: R1 to R2 and S1 to S2 (Slate blue/gray)
                    if (yR1 !== null && yR2 !== null) {
                        ctx.fillStyle = 'rgba(56, 189, 248, 0.05)';
                        ctx.fillRect(xStart, Math.min(yR1, yR2), w, Math.abs(yR1 - yR2));
                    }
                    if (yS1 !== null && yS2 !== null) {
                        ctx.fillStyle = 'rgba(56, 189, 248, 0.05)';
                        ctx.fillRect(xStart, Math.min(yS1, yS2), w, Math.abs(yS1 - yS2));
                    }
                    
                    // Outer zones: R2 to R3 and S2 to S3 (Forest green)
                    if (yR2 !== null && yR3 !== null) {
                        ctx.fillStyle = 'rgba(34, 197, 94, 0.06)';
                        ctx.fillRect(xStart, Math.min(yR2, yR3), w, Math.abs(yR2 - yR3));
                    }
                    if (yS2 !== null && yS3 !== null) {
                        ctx.fillStyle = 'rgba(34, 197, 94, 0.06)';
                        ctx.fillRect(xStart, Math.min(yS2, yS3), w, Math.abs(yS2 - yS3));
                    }
                }

                // Draw lines
                ctx.lineWidth = 1;

                // PP (Green dashed line)
                if (yPP !== null) {
                    ctx.strokeStyle = '#22c55e';
                    ctx.setLineDash([4, 4]);
                    ctx.beginPath(); ctx.moveTo(xStart, yPP); ctx.lineTo(xEnd, yPP); ctx.stroke();
                    ctx.setLineDash([]);
                }
                
                // R1 and S1 (slate gray)
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
                if (yR1 !== null) { ctx.beginPath(); ctx.moveTo(xStart, yR1); ctx.lineTo(xEnd, yR1); ctx.stroke(); }
                if (yS1 !== null) { ctx.beginPath(); ctx.moveTo(xStart, yS1); ctx.lineTo(xEnd, yS1); ctx.stroke(); }

                // R2 and S2 (Light blue)
                ctx.strokeStyle = 'rgba(56, 189, 248, 0.5)';
                if (yR2 !== null) { ctx.beginPath(); ctx.moveTo(xStart, yR2); ctx.lineTo(xEnd, yR2); ctx.stroke(); }
                if (yS2 !== null) { ctx.beginPath(); ctx.moveTo(xStart, yS2); ctx.lineTo(xEnd, yS2); ctx.stroke(); }

                // R3 and S3 (Green)
                ctx.strokeStyle = 'rgba(34, 197, 94, 0.6)';
                if (yR3 !== null) { ctx.beginPath(); ctx.moveTo(xStart, yR3); ctx.lineTo(xEnd, yR3); ctx.stroke(); }
                if (yS3 !== null) { ctx.beginPath(); ctx.moveTo(xStart, yS3); ctx.lineTo(xEnd, yS3); ctx.stroke(); }
            }
        }
        
        // 2. Draw all saved trendlines
        trendlines.forEach(tl => {
            const startPos = chartToPixel(tl.start);
            const endPos = chartToPixel(tl.end);
            if (startPos && endPos && startPos.x !== null && startPos.y !== null && endPos.x !== null && endPos.y !== null) {
                ctx.strokeStyle = '#a78bfa';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(startPos.x, startPos.y);
                ctx.lineTo(endPos.x, endPos.y);
                ctx.stroke();
                
                ctx.fillStyle = '#c084fc';
                ctx.beginPath(); ctx.arc(startPos.x, startPos.y, 4, 0, 2 * Math.PI); ctx.fill();
                ctx.beginPath(); ctx.arc(endPos.x, endPos.y, 4, 0, 2 * Math.PI); ctx.fill();
            }
        });
        
        // 3. Draw active drawing trendline
        if (activeTool === 'trendline' && isDrawing && drawStart && drawCurrent) {
            const startPos = chartToPixel(drawStart);
            const endPos = chartToPixel(drawCurrent);
            if (startPos && endPos && startPos.x !== null && startPos.y !== null && endPos.x !== null && endPos.y !== null) {
                ctx.strokeStyle = 'rgba(167, 139, 250, 0.6)';
                ctx.lineWidth = 2;
                ctx.setLineDash([5, 5]);
                ctx.beginPath();
                ctx.moveTo(startPos.x, startPos.y);
                ctx.lineTo(endPos.x, endPos.y);
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }
        
        // 4. Draw saved measurement
        if (measurement) {
            drawMeasurementBox(ctx, measurement.start, measurement.end, false);
        }
        
        // 5. Draw active drawing measurement
        if (activeTool === 'measure' && isDrawing && drawStart && drawCurrent) {
            drawMeasurementBox(ctx, drawStart, drawCurrent, true);
        }
    }

    // Initialize TradingView Candlestick Chart
    // Initialize TradingView Candlestick Chart
    function initChart() {
        logToConsole("initChart starting...", "info");
        if (!chartContainer) {
            logToConsole("initChart aborted: chartContainer element not found!", "error");
            return;
        }
        
        // Remove empty state only (preserves chartLegend element)
        const emptyState = document.getElementById('emptyChartState');
        if (emptyState) emptyState.remove();

        const width = chartContainer.clientWidth;
        const height = chartContainer.clientHeight || 450;
        logToConsole(`initChart dimensions: ${width}x${height}`, "info");

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
            logToConsole("initChart: Chart created successfully.", "info");
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

        try {
            if (typeof chart.addCandlestickSeries === 'function') {
                candlestickSeries = chart.addCandlestickSeries(candlestickOptions);
                logToConsole("initChart: Created candlestickSeries via addCandlestickSeries.", "info");
            } else if (typeof chart.addSeries === 'function') {
                candlestickSeries = chart.addSeries(LightweightCharts.CandlestickSeries, candlestickOptions);
                logToConsole("initChart: Created candlestickSeries via addSeries.", "info");
            } else {
                logToConsole("initChart error: No series add method found on chart object!", "error");
            }
        } catch(err) {
            logToConsole(`initChart error adding candlestick series: ${err.message}`, "error");
        }

        // Version-agnostic volume overlay series creation (supports v4 and v5)
        const volumeOptions = {
            color: '#3b82f6',
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '', // Overlay main pane
        };

        try {
            if (typeof chart.addHistogramSeries === 'function') {
                volumeSeries = chart.addHistogramSeries(volumeOptions);
                logToConsole("initChart: Created volumeSeries via addHistogramSeries.", "info");
            } else if (typeof chart.addSeries === 'function') {
                volumeSeries = chart.addSeries(LightweightCharts.HistogramSeries, volumeOptions);
                logToConsole("initChart: Created volumeSeries via addSeries.", "info");
            } else {
                logToConsole("initChart error: No volume series add method found on chart object!", "error");
            }
        } catch(err) {
            logToConsole(`initChart error adding volume series: ${err.message}`, "error");
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

        // Dynamic crosshair movement legend updates and RSI crosshair sync
        chart.subscribeCrosshairMove(param => {
            if (!param.point || !param.time || param.point.x < 0 || param.point.x > chartContainer.clientWidth || param.point.y < 0 || param.point.y > chartContainer.clientHeight) {
                showLastBarData();
                if (!isMovingCrosshair && rsiChart) {
                    isMovingCrosshair = true;
                    rsiChart.clearCrosshairPosition();
                    isMovingCrosshair = false;
                }
                return;
            }
            
            const ohlc = param.seriesData.get(candlestickSeries);
            const volumeData = param.seriesData.get(volumeSeries);
            
            if (ohlc) {
                updateLegend(param.time, ohlc, volumeData ? volumeData.value : null);
            }

            // Sync with RSI chart crosshair
            if (!isMovingCrosshair && rsiChart && rsiSeries && param.time) {
                isMovingCrosshair = true;
                const rsiVal = param.seriesData.get(rsiSeries);
                const price = rsiVal ? rsiVal.value : 50;
                rsiChart.setCrosshairPosition(price, param.time, rsiSeries);
                isMovingCrosshair = false;
            }
        });

        // Setup drawing canvas size
        const drawingCanvas = document.getElementById('drawingCanvas');
        if (drawingCanvas) {
            drawingCanvas.width = chartContainer.clientWidth;
            drawingCanvas.height = chartContainer.clientHeight;
        }

        // Subscribe to timescale changes to redraw drawings
        chart.timeScale().subscribeVisibleTimeRangeChange(redrawCanvas);

        // Drawing events on overlay canvas
        if (drawingCanvas) {
            function getMousePos(e) {
                const rect = drawingCanvas.getBoundingClientRect();
                return {
                    x: e.clientX - rect.left,
                    y: e.clientY - rect.top
                };
            }

            drawingCanvas.addEventListener('mousedown', (e) => {
                if (activeTool === 'cursor') return;
                const pos = getMousePos(e);
                const time = chart.timeScale().coordinateToTime(pos.x);
                const price = candlestickSeries.coordinateToPrice(pos.y);
                
                if (time && price) {
                    isDrawing = true;
                    drawStart = { time, price };
                    drawCurrent = { time, price };
                }
            });

            drawingCanvas.addEventListener('mousemove', (e) => {
                if (!isDrawing || !drawStart) return;
                const pos = getMousePos(e);
                const time = chart.timeScale().coordinateToTime(pos.x);
                const price = candlestickSeries.coordinateToPrice(pos.y);
                
                if (time && price) {
                    drawCurrent = { time, price };
                    redrawCanvas();
                }
            });

            drawingCanvas.addEventListener('mouseup', (e) => {
                if (!isDrawing) return;
                isDrawing = false;
                const pos = getMousePos(e);
                const time = chart.timeScale().coordinateToTime(pos.x);
                const price = candlestickSeries.coordinateToPrice(pos.y);
                
                if (drawStart && time && price) {
                    const drawEnd = { time, price };
                    if (activeTool === 'trendline') {
                        trendlines.push({ start: drawStart, end: drawEnd });
                        logToConsole('Trendline added.', 'info');
                    } else if (activeTool === 'measure') {
                        measurement = { start: drawStart, end: drawEnd };
                        logToConsole('Price measurement completed.', 'info');
                    }
                }
                drawStart = null;
                drawCurrent = null;
                redrawCanvas();
                setActiveTool('cursor');
            });
        }

        // Make responsive to resize
        window.addEventListener('resize', () => {
            if (chart && chartContainer) {
                chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
                if (drawingCanvas) {
                    drawingCanvas.width = chartContainer.clientWidth;
                    drawingCanvas.height = chartContainer.clientHeight;
                }
                redrawCanvas();
                const rsiContainer = document.getElementById('rsiContainer');
                if (rsiChart && rsiContainer) {
                    rsiChart.resize(rsiContainer.clientWidth, rsiContainer.clientHeight);
                }
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
        logToConsole(`Status: chart exists = ${chart !== null}, candlestickSeries exists = ${candlestickSeries !== null}, volumeSeries exists = ${volumeSeries !== null}`, "info");
        
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
                if (candlestickSeries) {
                    candlestickSeries.setData(ohlcData);
                } else {
                    logToConsole("Error: candlestickSeries is null in loadStockChart!", "error");
                }
                if (volumeSeries) {
                    volumeSeries.setData(volData);
                } else {
                    logToConsole("Error: volumeSeries is null in loadStockChart!", "error");
                }
                
                // Adjust scale
                if (chart) {
                    chart.timeScale().fitContent();
                }
                
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
                
                // Reset drawing canvas and recalculate indicators
                trendlines = [];
                measurement = null;
                recalculateMAs();
                updateRSIPane();
                updatePivotLines();
                
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
            downloadedDatesList = data.downloaded_dates || [];
            databaseDatesList = data.database_dates || [];

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
        const fromVal = downloadFromDateInput.value;
        const toVal = downloadToDateInput.value;
        if (!fromVal || !toVal) {
            logToConsole('Please select a date range to download.', 'error');
            return;
        }

        if (new Date(fromVal) > new Date(toVal)) {
            logToConsole('From Date cannot be after To Date.', 'error');
            alert('From Date cannot be after To Date.');
            return;
        }

        // Generate target weekdays in JS to do local check
        const fromDate = new Date(fromVal);
        const toDate = new Date(toVal);
        const todayStr = formatISODate(new Date());
        
        let targetDates = [];
        let curr = new Date(fromDate);
        while (curr <= toDate) {
            const dateStr = formatISODate(curr);
            if (dateStr <= todayStr && curr.getDay() !== 0 && curr.getDay() !== 6) { // 0: Sunday, 6: Saturday
                targetDates.push(dateStr);
            }
            curr.setDate(curr.getDate() + 1);
        }

        // Check if all weekdays are already present in databaseDatesList
        const allAlreadyDownloaded = targetDates.length > 0 && targetDates.every(d => databaseDatesList.includes(d));
        if (allAlreadyDownloaded) {
            logToConsole('Download skipped: selected date range is already available in the database.', 'info');
            alert('Data is already available in the database.');
            return;
        }

        logToConsole(`Initiating download request for range: ${fromVal} to ${toVal}...`);
        loadingOverlay.style.display = 'flex';
        
        try {
            const response = await fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    from_date: fromVal,
                    to_date: toVal,
                    fallback: dateFallbackCheckbox.checked
                })
            });

            const result = await response.json();
            loadingOverlay.style.display = 'none';

            if (result.status === 'already_exists') {
                logToConsole(`Info: ${result.message}`, 'info');
                alert('Data is already available.');
                return;
            }

            if (response.ok && result.status === 'success') {
                logToConsole(`SUCCESS! Downloaded data up to: ${result.date}`, 'info');
                logToConsole(`Processed ${result.records_downloaded.toLocaleString('en-IN')} stocks.`, 'info');
                logToConsole(`Total database size now: ${result.total_database_records.toLocaleString('en-IN')} records.`, 'info');
                
                // Select and load the newly downloaded date
                activeDate = result.date;
                await loadDashboardStats(false);
                await viewDateData(activeDate);
                
                // If a stock chart is currently open, automatically reload it to show the fresh data
                if (currentSymbol) {
                    logToConsole(`Reloading chart for ${currentSymbol} with fresh data...`, 'info');
                    await loadStockChart(currentSymbol);
                }
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

    const barChartFromDate = document.getElementById('barChartFromDate');
    const barChartToDate = document.getElementById('barChartToDate');
    const btnScrollLeft = document.getElementById('btnScrollLeft');
    const btnScrollRight = document.getElementById('btnScrollRight');
    const backtestBarChartContainer = document.getElementById('backtestBarChartContainer');
    const backtestBarChartWrapper = document.getElementById('backtestBarChartWrapper');

    let watchlistSymbols = null;

    // --- Stock Screener Backtesting State ---
    let activeScreenerResults = null;
    let screenerDates = [];
    let activeScreenerDateIndex = -1;
    let backtestChart = null;

    // Scroll buttons for backtest chart
    btnScrollLeft.addEventListener('click', () => {
        backtestBarChartContainer.scrollBy({ left: -300, behavior: 'smooth' });
    });
    btnScrollRight.addEventListener('click', () => {
        backtestBarChartContainer.scrollBy({ left: 300, behavior: 'smooth' });
    });

    // Date range inputs to redraw chart
    const onChartFilterChange = () => {
        if (activeScreenerResults) {
            renderBacktestChart(activeScreenerResults, false);
        }
    };
    barChartFromDate.addEventListener('change', onChartFilterChange);
    barChartToDate.addEventListener('change', onChartFilterChange);

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
    function renderBacktestChart(historicalResults, resetFilters = true) {
        try {
            logToConsole("renderBacktestChart starting...", "info");
            const allDates = Object.keys(historicalResults).sort(); // Sort dates chronologically
            if (allDates.length === 0) {
                logToConsole("renderBacktestChart aborted: historicalResults is empty.", "info");
                return;
            }
            
            if (resetFilters) {
                barChartFromDate.value = allDates[0];
                barChartToDate.value = allDates[allDates.length - 1];
                
                barChartFromDate.min = allDates[0];
                barChartFromDate.max = allDates[allDates.length - 1];
                barChartToDate.min = allDates[0];
                barChartToDate.max = allDates[allDates.length - 1];
            }
            
            const fromFilter = barChartFromDate.value;
            const toFilter = barChartToDate.value;
            
            // Filter dates in range
            const dates = allDates.filter(d => d >= fromFilter && d <= toFilter);
            const counts = dates.map(dt => historicalResults[dt].length);
            
            logToConsole(`renderBacktestChart dates: ${JSON.stringify(dates)}`, "info");
            logToConsole(`renderBacktestChart counts: ${JSON.stringify(counts)}`, "info");

            screenerDates = dates;
            activeScreenerResults = historicalResults;
            
            // Show chart panel
            document.getElementById('screenerChartPanel').style.display = 'flex';
            
            // Dynamically adjust wrapper width for scrollability and bar size (60px per bar)
            const containerWidth = backtestBarChartContainer.clientWidth;
            const requiredWidth = Math.max(containerWidth, dates.length * 60);
            backtestBarChartWrapper.style.width = requiredWidth + 'px';
            logToConsole(`renderBacktestChart widths: container=${containerWidth}, required=${requiredWidth}`, "info");
            
            // Auto-scroll to the extreme right (most recent data) on render
            setTimeout(() => {
                backtestBarChartContainer.scrollLeft = requiredWidth;
            }, 100);
            
            if (backtestChart) {
                try {
                    backtestChart.destroy();
                } catch(err) {
                    console.error("Error destroying old chart:", err);
                }
            }
            
            // Recreate canvas with explicit width and height attributes to force Chart.js to render at the scrollable size
            backtestBarChartWrapper.innerHTML = `<canvas id="backtestBarChart" width="${requiredWidth}" height="180" style="width: ${requiredWidth}px; height: 180px;"></canvas>`;
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
                        borderRadius: 6,
                        barThickness: 32 // Large, easy-to-click bars
                    }]
                },
                options: {
                    responsive: false,
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
                            type: 'category',
                            grid: { display: false },
                            ticks: {
                                color: 'rgba(255, 255, 255, 0.4)',
                                font: { size: 10, weight: 'bold' },
                                maxRotation: 0,
                                minRotation: 0
                            }
                        },
                        y: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: {
                                color: 'rgba(255, 255, 255, 0.4)',
                                font: { size: 10 },
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
            logToConsole("renderBacktestChart: Chart created successfully.", "info");
        } catch(error) {
            logToConsole(`Error in renderBacktestChart: ${error.message}`, "error");
            console.error(error);
        }
    }

    // Display Screener Results for a specific Date
    function displayScreenerDateResults(dateStr) {
        if (!activeScreenerResults) return;

        const records = activeScreenerResults[dateStr] || [];
        
        let idx = screenerDates.indexOf(dateStr);
        if (idx !== -1) {
            activeScreenerDateIndex = idx;
        } else {
            activeScreenerDateIndex = -1;
        }

        // Show navigation controls if we have any matches in the filtered range
        if (screenerDates.length > 0) {
            document.getElementById('screenerNavigationControls').style.display = 'flex';
        } else {
            document.getElementById('screenerNavigationControls').style.display = 'none';
        }
        
        const parts = dateStr.split('-');
        const formattedDate = parts.length === 3 ? `${parts[2]}-${parts[1]}-${parts[0]}` : dateStr;
        
        document.getElementById('screenerActiveDateDisplay').textContent = formattedDate;
        document.getElementById('screenerResultsTitle').textContent = `Matches on`;
        document.getElementById('screenerResultsCount').textContent = `Found ${records.length} matches`;

        // Update button states
        if (activeScreenerDateIndex !== -1) {
            document.getElementById('btnPrevScreenerDate').disabled = (activeScreenerDateIndex <= 0);
            document.getElementById('btnNextScreenerDate').disabled = (activeScreenerDateIndex >= screenerDates.length - 1);
        } else {
            // Find if there is any date in screenerDates earlier or later
            const hasPrev = screenerDates.some(d => d < dateStr);
            const hasNext = screenerDates.some(d => d > dateStr);
            document.getElementById('btnPrevScreenerDate').disabled = !hasPrev;
            document.getElementById('btnNextScreenerDate').disabled = !hasNext;
        }
        
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

        if (records.length === 0) {
            screenerTableBody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">No stocks matched your screen conditions.</td>
                </tr>
            `;
            return;
        }

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
        } else if (activeScreenerDateIndex === -1 && screenerDates.length > 0) {
            // Find current displayed date
            const activeDateDisplay = document.getElementById('screenerActiveDateDisplay').textContent;
            const parts = activeDateDisplay.split('-');
            const dateStr = parts.length === 3 ? `${parts[2]}-${parts[1]}-${parts[0]}` : activeDateDisplay;
            
            // Find latest matching date before current date
            const prevDates = screenerDates.filter(d => d < dateStr);
            if (prevDates.length > 0) {
                displayScreenerDateResults(prevDates[prevDates.length - 1]);
            }
        }
    });

    document.getElementById('btnNextScreenerDate').addEventListener('click', () => {
        if (activeScreenerDateIndex !== -1 && activeScreenerDateIndex < screenerDates.length - 1) {
            displayScreenerDateResults(screenerDates[activeScreenerDateIndex + 1]);
        } else if (activeScreenerDateIndex === -1 && screenerDates.length > 0) {
            // Find current displayed date
            const activeDateDisplay = document.getElementById('screenerActiveDateDisplay').textContent;
            const parts = activeDateDisplay.split('-');
            const dateStr = parts.length === 3 ? `${parts[2]}-${parts[1]}-${parts[0]}` : activeDateDisplay;
            
            // Find earliest matching date after current date
            const nextDates = screenerDates.filter(d => d > dateStr);
            if (nextDates.length > 0) {
                displayScreenerDateResults(nextDates[0]);
            }
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

    // --- Drawing Toolbar Logic ---
    const toolCursor = document.getElementById('toolCursor');
    const toolTrendline = document.getElementById('toolTrendline');
    const toolMeasure = document.getElementById('toolMeasure');
    const btnClearDrawings = document.getElementById('btnClearDrawings');
    const drawingCanvas = document.getElementById('drawingCanvas');

    function setActiveTool(tool) {
        activeTool = tool;
        [toolCursor, toolTrendline, toolMeasure].forEach(btn => {
            if (btn) btn.classList.remove('active');
        });

        if (tool === 'cursor') {
            if (toolCursor) toolCursor.classList.add('active');
            if (drawingCanvas) drawingCanvas.style.pointerEvents = 'none';
        } else if (tool === 'trendline') {
            if (toolTrendline) toolTrendline.classList.add('active');
            if (drawingCanvas) drawingCanvas.style.pointerEvents = 'auto';
        } else if (tool === 'measure') {
            if (toolMeasure) toolMeasure.classList.add('active');
            if (drawingCanvas) drawingCanvas.style.pointerEvents = 'auto';
        }
    }

    if (toolCursor) toolCursor.addEventListener('click', () => setActiveTool('cursor'));
    if (toolTrendline) toolTrendline.addEventListener('click', () => setActiveTool('trendline'));
    if (toolMeasure) toolMeasure.addEventListener('click', () => setActiveTool('measure'));
    
    if (btnClearDrawings) {
        btnClearDrawings.addEventListener('click', () => {
            trendlines = [];
            measurement = null;
            redrawCanvas();
            logToConsole('Drawings cleared.', 'info');
        });
    }

    // --- Indicators Selector Panel ---
    const btnIndicatorsMenu = document.getElementById('btnIndicatorsMenu');
    const indicatorsPanel = document.getElementById('indicatorsPanel');

    if (btnIndicatorsMenu && indicatorsPanel) {
        btnIndicatorsMenu.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = indicatorsPanel.style.display === 'flex';
            indicatorsPanel.style.display = isOpen ? 'none' : 'flex';
        });

        indicatorsPanel.addEventListener('click', (e) => {
            e.stopPropagation(); // Keep open when clicking inside
        });

        document.addEventListener('click', () => {
            indicatorsPanel.style.display = 'none';
        });
    }

    // --- Moving Average Bindings ---
    const maTypeSelect = document.getElementById('maType');
    const maLengthInput = document.getElementById('maLength');
    const maColorInput = document.getElementById('maColor');
    const btnAddMA = document.getElementById('btnAddMA');
    const activeMAsList = document.getElementById('activeMAsList');

    if (btnAddMA) {
        btnAddMA.addEventListener('click', () => {
            const type = maTypeSelect.value;
            const length = parseInt(maLengthInput.value);
            const color = maColorInput.value;

            if (isNaN(length) || length < 2 || length > 500) {
                alert('Please enter a valid length between 2 and 500.');
                return;
            }

            if (activeMAs.length >= 5) {
                alert('You can add up to 5 Moving Averages.');
                return;
            }

            const id = Date.now().toString();
            activeMAs.push({ id, type, length, color, series: null });
            recalculateMAs();
            logToConsole(`Added ${type} (${length}) MA.`, 'info');
        });
    }

    function updateMABadges() {
        if (!activeMAsList) return;
        activeMAsList.innerHTML = '';
        activeMAs.forEach(ma => {
            const badge = document.createElement('div');
            badge.className = 'ma-badge';
            badge.style.borderColor = ma.color;
            badge.innerHTML = `
                <span style="color: ${ma.color};">&#9679;</span>
                <span>${ma.type} ${ma.length}</span>
                <span class="ma-delete" data-id="${ma.id}">&times;</span>
            `;
            badge.querySelector('.ma-delete').addEventListener('click', (e) => {
                e.stopPropagation();
                const id = e.target.getAttribute('data-id');
                const index = activeMAs.findIndex(m => m.id === id);
                if (index !== -1) {
                    const deleted = activeMAs.splice(index, 1)[0];
                    if (deleted.series && chart) {
                        try { chart.removeSeries(deleted.series); } catch(e) {}
                    }
                    updateMABadges();
                    logToConsole(`Removed ${deleted.type} (${deleted.length}) MA.`, 'info');
                }
            });
            activeMAsList.appendChild(badge);
        });
    }

    function recalculateMAs() {
        if (!chart || activeStockData.length === 0) return;
        activeMAs.forEach(ma => {
            if (ma.series) {
                try { chart.removeSeries(ma.series); } catch(e) {}
            }
            ma.series = chart.addLineSeries({
                color: ma.color,
                lineWidth: 1.5,
                title: `${ma.type} ${ma.length}`
            });
            const maData = (ma.type === 'SMA') 
                ? calculateSMA(activeStockData, ma.length) 
                : calculateEMA(activeStockData, ma.length);
            ma.series.setData(maData);
        });
        updateMABadges();
    }

    // --- RSI Bindings ---
    const toggleRSI = document.getElementById('toggleRSI');
    const rsiConfig = document.getElementById('rsiConfig');
    const rsiLengthInput = document.getElementById('rsiLength');
    const rsiColorInput = document.getElementById('rsiColor');

    if (toggleRSI) {
        toggleRSI.addEventListener('change', () => {
            rsiConfig.style.display = toggleRSI.checked ? 'flex' : 'none';
            updateRSIPane();
        });
    }

    if (rsiLengthInput) rsiLengthInput.addEventListener('change', updateRSIPane);
    if (rsiColorInput) rsiColorInput.addEventListener('change', updateRSIPane);

    // --- Pivot Points Bindings ---
    const togglePivots = document.getElementById('togglePivots');
    const pivotsConfig = document.getElementById('pivotsConfig');
    const pivotsShading = document.getElementById('pivotsShading');
    const pivotResColor = document.getElementById('pivotResColor');
    const pivotSupColor = document.getElementById('pivotSupColor');

    if (togglePivots) {
        togglePivots.addEventListener('change', () => {
            pivotsConfig.style.display = togglePivots.checked ? 'flex' : 'none';
            updatePivotLines();
        });
    }

    if (pivotsShading) pivotsShading.addEventListener('change', updatePivotLines);
    if (pivotResColor) pivotResColor.addEventListener('input', updatePivotLines);
    if (pivotSupColor) pivotSupColor.addEventListener('input', updatePivotLines);

    function updateRSIPane() {
        const toggleRSI = document.getElementById('toggleRSI');
        const rsiContainer = document.getElementById('rsiContainer');
        const rsiLengthInput = document.getElementById('rsiLength');
        const rsiColorInput = document.getElementById('rsiColor');

        if (!toggleRSI || !toggleRSI.checked || activeStockData.length === 0) {
            if (rsiContainer) rsiContainer.style.display = 'none';
            if (rsiChart) {
                try { rsiChart.remove(); } catch(e) {}
                rsiChart = null;
                rsiSeries = null;
            }
            return;
        }

        if (rsiContainer) rsiContainer.style.display = 'block';

        if (!rsiChart && rsiContainer) {
            rsiChart = LightweightCharts.createChart(rsiContainer, {
                width: rsiContainer.clientWidth,
                height: 140,
                layout: {
                    background: { type: 'solid', color: '#000000' },
                    textColor: '#94a3b8',
                    fontFamily: "'Inter', sans-serif",
                },
                grid: {
                    vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
                    horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
                },
                rightPriceScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    visible: true,
                    mode: LightweightCharts.PriceScaleMode.Normal,
                    autoScale: false,
                },
                timeScale: {
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    visible: false,
                },
            });

            rsiChart.priceScale('right').applyOptions({
                autoScale: false,
                scaleMargins: {
                    top: 0.1,
                    bottom: 0.1,
                },
            });

            // Sync visible time range
            chart.timeScale().subscribeVisibleTimeRangeChange(range => {
                if (range && rsiChart) rsiChart.timeScale().setVisibleRange(range);
            });

            // Sync price scale widths to align the timelines horizontally 1:1
            chart.priceScale('right').subscribeWidthChange(width => {
                if (rsiChart) {
                    rsiChart.priceScale('right').applyOptions({
                        minimumWidth: width,
                    });
                }
            });
            rsiChart.priceScale('right').subscribeWidthChange(width => {
                if (chart) {
                    chart.priceScale('right').applyOptions({
                        minimumWidth: width,
                    });
                }
            });

            // Sync crosshair from RSI chart to main chart
            rsiChart.subscribeCrosshairMove(param => {
                if (isMovingCrosshair || !chart || !candlestickSeries) return;
                isMovingCrosshair = true;
                if (param.time) {
                    const ohlc = param.seriesData.get(candlestickSeries);
                    const price = ohlc ? ohlc.close : 0;
                    chart.setCrosshairPosition(price, param.time, candlestickSeries);
                } else {
                    chart.clearCrosshairPosition();
                }
                isMovingCrosshair = false;
            });
        }

        if (rsiChart) {
            if (rsiSeries) {
                try { rsiChart.removeSeries(rsiSeries); } catch(e) {}
            }

            const rsiLength = parseInt(rsiLengthInput.value) || 14;
            const rsiColor = rsiColorInput.value;

            rsiSeries = rsiChart.addLineSeries({
                color: rsiColor,
                lineWidth: 1.5,
                title: `RSI ${rsiLength}`
            });

            rsiSeries.createPriceLine({
                price: 70,
                color: '#ef4444',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: true,
                title: '70'
            });

            rsiSeries.createPriceLine({
                price: 30,
                color: '#10b981',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: true,
                title: '30'
            });

            const rsiData = calculateRSI(activeStockData, rsiLength);
            rsiSeries.setData(rsiData);

            // Sync visible range
            const range = chart.timeScale().getVisibleRange();
            if (range) rsiChart.timeScale().setVisibleRange(range);
        }
    }

    function updatePivotLines() {
        redrawCanvas();
    }

    // --- Saved Strategies Management ---
    const selectStrategy = document.getElementById('selectStrategy');
    const btnSaveStrategy = document.getElementById('btnSaveStrategy');
    const btnDeleteStrategy = document.getElementById('btnDeleteStrategy');
    const saveStrategyName = document.getElementById('saveStrategyName');
    const btnExportScreenerExcel = document.getElementById('btnExportScreenerExcel');

    let loadedStrategies = [];

    async function loadStrategies() {
        if (!selectStrategy) return;
        try {
            const response = await fetch('/api/screener/strategies');
            const result = await response.json();
            if (result.status === 'success') {
                loadedStrategies = result.strategies;
                
                // Keep the default option
                selectStrategy.innerHTML = '<option value="">-- Choose saved strategy --</option>';
                loadedStrategies.forEach(s => {
                    const opt = document.createElement('option');
                    opt.value = s.name;
                    opt.textContent = s.name;
                    selectStrategy.appendChild(opt);
                });
            }
        } catch(err) {
            logToConsole(`Error loading strategies: ${err.message}`, 'error');
        }
    }

    if (selectStrategy) {
        selectStrategy.addEventListener('change', () => {
            const val = selectStrategy.value;
            if (!val) return;
            const strat = loadedStrategies.find(s => s.name === val);
            if (strat && screenerCode) {
                screenerCode.value = strat.code;
                logToConsole(`Loaded strategy: '${val}'`, 'info');
            }
        });
    }

    if (btnSaveStrategy) {
        btnSaveStrategy.addEventListener('click', async () => {
            const name = saveStrategyName.value.trim();
            const code = screenerCode.value;

            if (!name) {
                alert('Please enter a strategy name.');
                return;
            }

            logToConsole(`Saving strategy '${name}'...`);
            try {
                const response = await fetch('/api/screener/strategies', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, code })
                });
                const result = await response.json();
                if (result.status === 'success') {
                    logToConsole(result.message, 'info');
                    alert(result.message);
                    saveStrategyName.value = '';
                    await loadStrategies();
                    selectStrategy.value = name;
                } else {
                    logToConsole(result.message, 'error');
                    alert(`Save failed: ${result.message}`);
                }
            } catch(err) {
                logToConsole(`Network error saving strategy: ${err.message}`, 'error');
            }
        });
    }

    if (btnDeleteStrategy) {
        btnDeleteStrategy.addEventListener('click', async () => {
            const val = selectStrategy.value;
            if (!val) {
                alert('Please select a strategy to delete.');
                return;
            }

            if (!confirm(`Are you sure you want to delete the strategy '${val}'?`)) {
                return;
            }

            logToConsole(`Deleting strategy '${val}'...`);
            try {
                const response = await fetch(`/api/screener/strategies/${encodeURIComponent(val)}`, {
                    method: 'DELETE'
                });
                const result = await response.json();
                if (result.status === 'success') {
                    logToConsole(result.message, 'info');
                    alert(result.message);
                    await loadStrategies();
                } else {
                    logToConsole(result.message, 'error');
                    alert(`Delete failed: ${result.message}`);
                }
            } catch(err) {
                logToConsole(`Network error deleting strategy: ${err.message}`, 'error');
            }
        });
    }

    // --- Export Screener Results to Excel/CSV ---
    if (btnExportScreenerExcel) {
        btnExportScreenerExcel.addEventListener('click', async () => {
            if (!screenerDates || screenerDates.length === 0 || activeScreenerDateIndex < 0) {
                alert('No screener matches available to export.');
                return;
            }

            const activeDateStr = screenerDates[activeScreenerDateIndex];
            const results = activeScreenerResults[activeDateStr];

            if (!results || results.length === 0) {
                alert('No matches found on the active date to export.');
                return;
            }

            logToConsole(`Exporting ${results.length} matches for date ${activeDateStr}...`);
            btnExportScreenerExcel.disabled = true;
            const originalBtnHtml = btnExportScreenerExcel.innerHTML;
            btnExportScreenerExcel.textContent = 'Exporting...';

            try {
                const response = await fetch('/api/screener/export', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ date: activeDateStr, results: results })
                });

                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    
                    const disposition = response.headers.get('content-disposition');
                    let filename = `screener_results_${activeDateStr}.xlsx`;
                    if (disposition && disposition.indexOf('attachment') !== -1) {
                        const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                        const matches = filenameRegex.exec(disposition);
                        if (matches != null && matches[1]) { 
                            filename = matches[1].replace(/['"]/g, '');
                        }
                    }
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    logToConsole('Screener results exported successfully.', 'info');
                } else {
                    const errRes = await response.json();
                    logToConsole(`Export failed: ${errRes.message}`, 'error');
                    alert(`Export failed: ${errRes.message}`);
                }
            } catch(err) {
                logToConsole(`Network error during export: ${err.message}`, 'error');
                alert(`Export error: ${err.message}`);
            } finally {
                btnExportScreenerExcel.disabled = false;
                btnExportScreenerExcel.innerHTML = originalBtnHtml;
            }
        });
    }

    // Initialize Dashboard & Chart
    initChart();
    loadStockSymbols();
    loadDashboardStats(true);
    loadStrategies();
});

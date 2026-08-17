const { createApp, ref, reactive, computed, onMounted, onUnmounted, nextTick, watch, provide, inject } = Vue;

const API_BASE = '/api';

function fmt(val, decimals = 2) {
    if (val == null || val === '') return '-';
    if (typeof val === 'number') {
        if (decimals === 2) return val.toFixed(2);
        if (decimals === 4) return val.toFixed(4);
    }
    return val;
}

function fmtMoney(val) {
    if (val == null || val === '') return '-';
    const num = Number(val);
    if (Math.abs(num) >= 1e8) return (num / 1e8).toFixed(2) + '亿';
    if (Math.abs(num) >= 1e4) return (num / 1e4).toFixed(2) + '万';
    return num.toFixed(2);
}

function fmtGrowth(val) {
    if (val == null || val === '') return '-';
    const prefix = val > 0 ? '+' : '';
    return prefix + Number(val).toFixed(2) + '%';
}

function valClass(val) {
    if (val == null) return '';
    return val > 0 ? 'up' : (val < 0 ? 'down' : '');
}

const app = createApp({
    setup() {
        const currentPage = ref('screening');
        const pages = [
            { id: 'strong', label: '强势板块', icon: '▲' },
            { id: 'strong_stocks', label: '强势个股', icon: '★' },
            { id: 'screening', label: '选股策略', icon: '⊞' },
            { id: 'vcp', label: 'VCP波动收缩', icon: '◐' },
            { id: 'bt_strategies', label: '回测策略', icon: '⇄' },
            { id: 'profile', label: '股票画像', icon: '◈' },
            { id: 'dividend', label: '分红列表', icon: '❖' },
            { id: 'debate', label: 'AI多空辩论', icon: '⚖' },
            { id: 'expert', label: '蒸馏专家', icon: '⚗' },
            { id: 'dmdl', label: '估值榜', icon: '⚖' },
            { id: 'query', label: '智能问数', icon: '✦' },
            { id: 'data_mgmt', label: '数据管理', icon: '⚙' },
            { id: 'data_catalog', label: '数据资产', icon: '🗂' },
            { id: 'data_lineage', label: '数据血缘', icon: '⛓' },
        ];
        const navPages = computed(() => pages);
        provide('currentPage', currentPage);
        return { currentPage, pages, navPages };
    },
});

app.component('screening-page', {
    template: '#screening-tpl',
    setup() {
        const currentPage = inject('currentPage');
        const strategies = ref({ technical: [], fundamental: [], combined: [] });
        const tabType = ref('technical');
        const selectedStrategy = ref(null);
        const loading = ref(false);
        const result = ref(null);
        const error = ref('');
        const maPeriods = ref('5,10,20,60');
        const consolidationDays = ref(20);
        const revenueThreshold = ref(20);
        const profitThreshold = ref(20);
        const debtThreshold = ref(50);
        const lookbackMonths = ref(2);
        const volumeRatioMin = ref(1.5);
        const volumeRatioMax = ref(4.0);
        const shrinkDays = ref(3);
        const minGapDays = ref(3);
        const maxGapDays = ref(10);
        const consecutiveYears = ref(5);
        const profitMinYi = ref(10);
        const profitMaxYi = ref(null);
        const strictness = ref('standard');
        const requireConfirm = ref(false);
        const selectedStock = ref(null);
        const stockDetail = ref(null);
        const detailLoading = ref(false);
        const detailChartRef = ref(null);
        let detailChart = null;
        const industryFilter = ref('all');
        const sortColumn = ref(null);
        const sortDirection = ref('');

        const filteredRows = computed(() => {
            if (!result.value || !result.value.rows) return [];
            if (industryFilter.value === 'all') return result.value.rows;
            return result.value.rows.filter(r => {
                const sectors = (r.industry_sectors || '').split(',');
                return sectors.some(s => s === industryFilter.value);
            });
        });

        const sortedRows = computed(() => {
            const base = tabType.value === 'volume_surge' ? filteredRows.value : (result.value?.rows || []);
            if (!sortColumn.value || !base.length) return base;
            const dir = sortDirection.value === 'desc' ? -1 : 1;
            const col = sortColumn.value;
            return [...base].sort((a, b) => {
                const av = a[col], bv = b[col];
                if (av == null && bv == null) return 0;
                if (av == null) return 1;
                if (bv == null) return -1;
                if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
                return String(av).localeCompare(String(bv), 'zh-Hans-CN', { numeric: true }) * dir;
            });
        });

        function sortBy(col) {
            if (sortColumn.value === col) {
                if (sortDirection.value === 'asc') sortDirection.value = 'desc';
                else { sortColumn.value = null; sortDirection.value = ''; }
            } else {
                sortColumn.value = col;
                sortDirection.value = 'asc';
            }
        }

        const industryOptions = computed(() => {
            if (!result.value || !result.value.rows) return [];
            const set = new Set();
            for (const r of result.value.rows) {
                const sectors = (r.industry_sectors || '').split(',').filter(Boolean);
                for (const s of sectors) set.add(s);
            }
            return [...set].sort();
        });

        const currentStockIndex = computed(() => {
            if (!selectedStock.value || !filteredRows.value) return -1;
            return filteredRows.value.findIndex(r => r.stock_code === selectedStock.value.stock_code);
        });
        const hasPrev = computed(() => currentStockIndex.value > 0);
        const hasNext = computed(() => {
            if (!filteredRows.value) return false;
            return currentStockIndex.value < filteredRows.value.length - 1;
        });

        onMounted(async () => {
            try {
                const r = await fetch(`${API_BASE}/screening/strategies`);
                strategies.value = await r.json();
            } catch (e) {
                error.value = '加载策略列表失败: ' + e.message;
            }
        });

        const currentStrategies = computed(() => strategies.value[tabType.value] || []);
        const hasResult = computed(() => result.value && result.value.rows && result.value.rows.length > 0);

        function selectStrategy(id) { selectedStrategy.value = id; result.value = null; error.value = ''; sortColumn.value = null; sortDirection.value = ''; nextTick(() => execute()); }

        function switchToTurnaround() {
            tabType.value = 'turnaround';
            selectedStrategy.value = 'turnaround';
            revenueThreshold.value = 15;
            profitThreshold.value = 10;
            debtThreshold.value = 20;
            result.value = null;
            error.value = '';
            nextTick(() => execute());
        }

        async function execute() {
            if (!selectedStrategy.value) return;
            loading.value = true; error.value = ''; result.value = null;
            sortColumn.value = null; sortDirection.value = '';
            const params = new URLSearchParams();
            params.set('strategy_id', selectedStrategy.value);
            params.set('ma_periods', maPeriods.value);
            params.set('revenue_threshold', revenueThreshold.value);
            params.set('profit_threshold', profitThreshold.value);
            params.set('debt_threshold', debtThreshold.value);
            params.set('consolidation_days', consolidationDays.value);
            params.set('lookback_months', lookbackMonths.value);
            params.set('volume_ratio_min', volumeRatioMin.value);
            params.set('volume_ratio_max', volumeRatioMax.value);
            params.set('shrink_days', shrinkDays.value);
            params.set('min_gap_days', minGapDays.value);
            params.set('max_gap_days', maxGapDays.value);
            params.set('consecutive_years', consecutiveYears.value);
            params.set('profit_min_yi', profitMinYi.value);
            if (profitMaxYi.value !== null && profitMaxYi.value !== '') params.set('profit_max_yi', profitMaxYi.value);
            params.set('strictness', strictness.value);
            params.set('require_confirm', requireConfirm.value ? 'true' : 'false');
            try {
                const r = await fetch(`${API_BASE}/screening/execute?${params}`, { method: 'POST' });
                const data = await r.json();
                if (data.error) error.value = data.error; else result.value = data;
            } catch (e) { error.value = '请求失败: ' + e.message; }
            finally { loading.value = false; }
        }

        function isSelected(id) { return selectedStrategy.value === id; }

        async function selectStock(row) {
            if (tabType.value !== 'volume_surge') return;
            selectedStock.value = row;
            stockDetail.value = null;
            detailLoading.value = true;
            try {
                const params = new URLSearchParams({
                    lookback_months: lookbackMonths.value,
                    volume_ratio_min: volumeRatioMin.value,
                    volume_ratio_max: volumeRatioMax.value,
                    shrink_days: shrinkDays.value,
                    min_gap_days: minGapDays.value,
                    max_gap_days: maxGapDays.value,
                });
                const r = await fetch(`${API_BASE}/volume-surge/detail/${row.stock_code}?${params}`);
                const data = await r.json();
                if (!data.error) {
                    stockDetail.value = data;
                    await nextTick();
                    renderDetailChart(data);
                }
            } catch (e) {
                console.error(e);
            } finally {
                detailLoading.value = false;
            }
        }

        async function renderDetailChart(detail) {
            if (!detailChartRef.value || !detail.stock_code) return;
            if (detailChart) { detailChart.remove(); detailChart = null; }

            const klineR = await fetch(`${API_BASE}/kline/${detail.stock_code}?days=120`);
            const klineData = await klineR.json();
            const kline = (klineR.ok ? klineData.rows : []).map(d => ({
                time: d.trade_date.substring(0, 10),
                open: Number(d.open_price),
                high: Number(d.high_price),
                low: Number(d.low_price),
                close: Number(d.close_price),
                volume: Number(d.volume),
            }));
            kline.sort((a, b) => a.time.localeCompare(b.time));

            detailChart = LightweightCharts.createChart(detailChartRef.value, {
                width: detailChartRef.value.clientWidth,
                height: 420,
                layout: { background: { type: 'solid', color: '#111827' }, textColor: '#64748b' },
                grid: { vertLines: { color: '#1e3a5f' }, horzLines: { color: '#1e3a5f' } },
                crosshair: { mode: 0 },
                timeScale: { borderColor: '#1e3a5f', timeVisible: false },
                rightPriceScale: { borderColor: '#1e3a5f' },
            });

            const candleSeries = detailChart.addCandlestickSeries({
                upColor: '#ef4444', downColor: '#10b981',
                borderDownColor: '#10b981', borderUpColor: '#ef4444',
                wickDownColor: '#10b981', wickUpColor: '#ef4444',
            });
            candleSeries.setData(kline);

            const volSeries = detailChart.addHistogramSeries({
                color: '#3a6ea5', priceFormat: { type: 'volume' },
                priceScaleId: 'volume',
            });
            detailChart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
            volSeries.setData(kline.map(d => ({
                time: d.time,
                value: d.volume,
                color: d.close >= d.open ? '#ef444466' : '#10b98166',
            })));

            const markers = [];
            const kingDates = new Set();
            if (detail.all_king_surges) {
                for (const k of detail.all_king_surges) {
                    kingDates.add(k.date.substring(0, 10));
                    markers.push({
                        time: k.date.substring(0, 10),
                        position: 'belowBar',
                        color: '#f59e0b',
                        shape: 'arrowUp',
                        text: '王' + k.king_index,
                    });
                }
            }
            if (detail.surges) {
                for (const s of detail.surges) {
                    const dateStr = s.trade_date ? s.trade_date.substring(0, 10) : '';
                    if (dateStr && !kingDates.has(dateStr)) {
                        markers.push({
                            time: dateStr,
                            position: 'aboveBar',
                            color: '#f59e0b',
                            shape: 'circle',
                            text: '倍',
                        });
                    }
                }
            }
            markers.sort((a, b) => a.time.localeCompare(b.time));
            candleSeries.setMarkers(markers);
            detailChart.timeScale().fitContent();
        }

        function closeDetail() {
            selectedStock.value = null;
            stockDetail.value = null;
            if (detailChart) { detailChart.remove(); detailChart = null; }
        }

        function navigateStock(direction) {
            const rows = filteredRows.value;
            if (!rows || rows.length === 0) return;
            const idx = currentStockIndex.value;
            const newIdx = idx + direction;
            if (newIdx >= 0 && newIdx < rows.length) {
                selectStock(rows[newIdx]);
            }
        }

        function prevStock() { navigateStock(-1); }
        function nextStock() { navigateStock(1); }

        function goToProfileFromScreening(row) {
            window._profileStockCode = row.stock_code;
            window._screeningList = result.value && result.value.rows ? result.value.rows : [];
            currentPage.value = 'profile';
        }

        function handleKeydown(e) {
            if (tabType.value !== 'volume_surge') return;
            if (!selectedStock.value) return;
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            if (e.key === 'ArrowLeft') { e.preventDefault(); prevStock(); }
            if (e.key === 'ArrowRight') { e.preventDefault(); nextStock(); }
        }

        onMounted(() => {
            document.addEventListener('keydown', handleKeydown);
        });

        onUnmounted(() => {
            document.removeEventListener('keydown', handleKeydown);
        });

        return {
            strategies, tabType, selectedStrategy, loading, result, error,
            maPeriods, consolidationDays, revenueThreshold, profitThreshold, debtThreshold,
            lookbackMonths, volumeRatioMin, volumeRatioMax, shrinkDays, minGapDays, maxGapDays,
            consecutiveYears, profitMinYi, profitMaxYi, strictness, requireConfirm,
            selectedStock, stockDetail, detailLoading, detailChartRef,
            industryFilter, filteredRows, industryOptions,
            sortedRows, sortBy, sortColumn, sortDirection,
            currentStrategies, hasResult, currentStockIndex, hasPrev, hasNext,
            selectStrategy, execute, isSelected, switchToTurnaround,
            selectStock, closeDetail, prevStock, nextStock,
            goToProfileFromScreening,
            fmt, fmtGrowth, fmtMoney, valClass,
        };
    },
});

// ── Position Backtest ──
app.component('position-bt-page', {
    template: '#position-bt-tpl',
    setup() {
        const stockCode = ref('600519');
        const stockName = ref('');
        const klineDays = ref(500);
        const klineLoading = ref(false);
        const chartData = ref([]);
        const chartRef = ref(null);
        const tradeDirection = ref('buy');
        const trades = ref([]);
        const btLoading = ref(false);
        const btResult = ref({});
        const pnlPage = ref(1);
        const PNL_PAGE_SIZE = 20;

        let chartInstance = null;
        let candleSeries = null;

        async function loadKline() {
            if (!stockCode.value) return;
            klineLoading.value = true;
            try {
                const r = await fetch(`${API_BASE}/kline/${stockCode.value}?days=${klineDays.value}`);
                const data = await r.json();
                stockName.value = data.stock_name || '';
                chartData.value = (data.rows || []).map(d => ({
                    time: d.trade_date.substring(0, 10),
                    open: Number(d.open_price),
                    high: Number(d.high_price),
                    low: Number(d.low_price),
                    close: Number(d.close_price),
                    volume: Number(d.volume),
                }));
                chartData.value.sort((a, b) => a.time.localeCompare(b.time));
                renderChart();
            } catch (e) {
                console.error(e);
            } finally {
                klineLoading.value = false;
            }
        }

        function renderChart() {
            if (!chartRef.value || !chartData.value.length) return;
            if (chartInstance) chartInstance.remove();

            chartInstance = LightweightCharts.createChart(chartRef.value, {
                width: chartRef.value.clientWidth,
                height: 400,
                layout: {
                    background: { type: 'solid', color: '#111827' },
                    textColor: '#64748b',
                },
                grid: {
                    vertLines: { color: '#1e3a5f' },
                    horzLines: { color: '#1e3a5f' },
                },
                crosshair: { mode: 0 },
                timeScale: { borderColor: '#1e3a5f', timeVisible: false },
                rightPriceScale: { borderColor: '#1e3a5f' },
            });

            candleSeries = chartInstance.addCandlestickSeries({
                upColor: '#ef4444',
                downColor: '#10b981',
                borderDownColor: '#10b981',
                borderUpColor: '#ef4444',
                wickDownColor: '#10b981',
                wickUpColor: '#ef4444',
            });

            candleSeries.setData(chartData.value);
            chartInstance.timeScale().fitContent();

            chartInstance.subscribeClick(param => {
                if (!param.time) return;
                const timeStr = typeof param.time === 'string' ? param.time : param.time.year + '-' + String(param.time.month).padStart(2,'0') + '-' + String(param.time.day).padStart(2,'0');
                const candle = chartData.value.find(d => d.time === timeStr);
                if (!candle) return;
                const exists = trades.value.some(t => t.date === timeStr && t.direction === tradeDirection.value);
                if (exists) return;
                trades.value.push({
                    date: timeStr,
                    direction: tradeDirection.value,
                    shares: 100,
                    price: candle.close,
                });
                updateChartMarkers();
            });

            window.addEventListener('resize', () => {
                if (chartRef.value && chartInstance) {
                    chartInstance.applyOptions({ width: chartRef.value.clientWidth });
                }
            });
        }

        function updateChartMarkers() {
            if (!candleSeries) return;
            const markers = [];
            const seen = new Set();
            for (const t of trades.value) {
                const key = t.date + t.direction;
                if (seen.has(key)) continue;
                seen.add(key);
                markers.push({
                    time: t.date,
                    position: t.direction === 'buy' ? 'belowBar' : 'aboveBar',
                    color: t.direction === 'buy' ? '#10b981' : '#ef4444',
                    shape: t.direction === 'buy' ? 'arrowUp' : 'arrowDown',
                    text: t.direction === 'buy' ? 'B' : 'S',
                });
            }
            candleSeries.setMarkers(markers);
        }

        function deleteTrade(idx) {
            trades.value.splice(idx, 1);
            updateChartMarkers();
        }

        const paginatedPnl = computed(() => {
            if (!btResult.value.daily_pnl) return [];
            const start = (pnlPage.value - 1) * PNL_PAGE_SIZE;
            return btResult.value.daily_pnl.slice(start, start + PNL_PAGE_SIZE);
        });

        const pnlTotalPages = computed(() => {
            if (!btResult.value.daily_pnl) return 1;
            return Math.max(1, Math.ceil(btResult.value.daily_pnl.length / PNL_PAGE_SIZE));
        });

        async function runPositionBt() {
            if (!trades.value.length) return;
            btLoading.value = true;
            btResult.value = {};
            try {
                const r = await fetch(`${API_BASE}/backtest/position`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ stock_code: stockCode.value, trades: trades.value }),
                });
                btResult.value = await r.json();
                pnlPage.value = 1;
            } catch (e) {
                console.error(e);
            } finally {
                btLoading.value = false;
            }
        }

        return {
            stockCode, stockName, klineDays, klineLoading, chartData, chartRef,
            tradeDirection, trades, btLoading, btResult,
            pnlPage, paginatedPnl, pnlTotalPages,
            loadKline, deleteTrade, runPositionBt,
            fmt, fmtMoney,
        };
    },
});

// ── MA Backtest ──
app.component('ma-bt-page', {
    template: '#ma-bt-tpl',
    setup() {
        const maStockCode = ref('600519');
        const maStartDate = ref('');
        const maEndDate = ref('');
        const maShort = ref(5);
        const maLong = ref(20);
        const maAmount = ref(10000);
        const maLoading = ref(false);
        const maResult = ref({});
        const maChartRef = ref(null);

        onMounted(() => {
            const today = new Date();
            const end = today.toISOString().split('T')[0];
            const start = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate()).toISOString().split('T')[0];
            maEndDate.value = end;
            maStartDate.value = start;
        });

        async function runMaBt() {
            if (!maStockCode.value || !maStartDate.value || !maEndDate.value) return;
            maLoading.value = true;
            maResult.value = {};
            try {
                const params = new URLSearchParams({
                    stock_code: maStockCode.value,
                    start_date: maStartDate.value,
                    end_date: maEndDate.value,
                    short_ma: maShort.value,
                    long_ma: maLong.value,
                    total_capital: maAmount.value,
                });
                const r = await fetch(`${API_BASE}/backtest/ma?${params}`, { method: 'POST' });
                maResult.value = await r.json();
                await nextTick();
                renderMaChart();
            } catch (e) {
                console.error(e);
            } finally {
                maLoading.value = false;
            }
        }

        function renderMaChart() {
            if (!maChartRef.value || !maResult.value.daily || !maResult.value.daily.length) return;

            const container = maChartRef.value;
            if (container._chart) container._chart.remove();

            const chart = LightweightCharts.createChart(container, {
                width: container.clientWidth,
                height: 400,
                layout: {
                    background: { type: 'solid', color: '#111827' },
                    textColor: '#64748b',
                },
                grid: {
                    vertLines: { color: '#1e3a5f' },
                    horzLines: { color: '#1e3a5f' },
                },
                crosshair: { mode: 0 },
                timeScale: { borderColor: '#1e3a5f' },
                rightPriceScale: { borderColor: '#1e3a5f' },
            });
            container._chart = chart;

            const candleSeries = chart.addCandlestickSeries({
                upColor: '#ef4444', downColor: '#10b981',
                borderDownColor: '#10b981', borderUpColor: '#ef4444',
                wickDownColor: '#10b981', wickUpColor: '#ef4444',
            });

            const klineData = (maResult.value._kline || maResult.value.daily).map(d => ({
                time: d.date,
                open: Number(d.open_price || d.close_price),
                high: Number(d.high_price || d.close_price),
                low: Number(d.low_price || d.close_price),
                close: Number(d.close_price),
            }));

            // Get actual kline data with OHLC
            fetch(`${API_BASE}/kline_range/${maStockCode.value}?start_date=${maStartDate.value}&end_date=${maEndDate.value}`)
                .then(r => r.json())
                .then(data => {
                    const ohlc = (data.rows || []).map(d => ({
                        time: d.trade_date.substring(0, 10),
                        open: Number(d.open_price),
                        high: Number(d.high_price),
                        low: Number(d.low_price),
                        close: Number(d.close_price),
                    }));
                    if (ohlc.length) candleSeries.setData(ohlc);
                    else candleSeries.setData(klineData);
                })
                .catch(() => candleSeries.setData(klineData));

            // Dummy OHLC from daily close
            const closeOnly = (maResult.value.daily || []).map(d => ({
                time: d.date,
                open: Number(d.close_price),
                high: Number(d.close_price),
                low: Number(d.close_price),
                close: Number(d.close_price),
            }));
            if (!maResult.value._kline) {
                fetch(`${API_BASE}/kline_range/${maStockCode.value}?start_date=${maStartDate.value}&end_date=${maEndDate.value}`)
                    .then(r => r.json())
                    .then(data => {
                        const ohlc = (data.rows || []).map(d => ({
                            time: d.trade_date.substring(0, 10),
                            open: Number(d.open_price),
                            high: Number(d.high_price),
                            low: Number(d.low_price),
                            close: Number(d.close_price),
                        }));
                        candleSeries.setData(ohlc);
                    })
                    .catch(() => candleSeries.setData(closeOnly));
            }

            // MA lines
            const shortData = [];
            const longData = [];
            const dailyLen = maResult.value.daily.length;
            for (let i = 0; i < dailyLen; i++) {
                const d = maResult.value.daily[i];
                if (i + 1 >= maShort.value) {
                    let sum = 0;
                    for (let j = i - maShort.value + 1; j <= i; j++) sum += Number(maResult.value.daily[j].close_price);
                    shortData.push({ time: d.date, value: sum / maShort.value });
                }
                if (i + 1 >= maLong.value) {
                    let sum = 0;
                    for (let j = i - maLong.value + 1; j <= i; j++) sum += Number(maResult.value.daily[j].close_price);
                    longData.push({ time: d.date, value: sum / maLong.value });
                }
            }

            const shortLine = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, title: `MA${maShort.value}` });
            const longLine = chart.addLineSeries({ color: '#7c3aed', lineWidth: 1, title: `MA${maLong.value}` });
            shortLine.setData(shortData);
            longLine.setData(longData);

            // Trade markers
            const markers = [];
            for (const t of maResult.value.trades || []) {
                markers.push({ time: t.entry_date, position: 'belowBar', color: '#10b981', shape: 'arrowUp', text: 'B' });
                if (t.exit_date) markers.push({ time: t.exit_date, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'S' });
            }
            candleSeries.setMarkers(markers);
            chart.timeScale().fitContent();

            window.addEventListener('resize', () => {
                if (container && container._chart) {
                    container._chart.applyOptions({ width: container.clientWidth });
                }
            });
        }

        return {
            maStockCode, maStartDate, maEndDate, maShort, maLong, maAmount,
            maLoading, maResult, maChartRef, runMaBt, fmt, fmtMoney,
        };
    },
});

app.component('bt-strategies-page', {
    template: '#bt-strategies-tpl',
});

app.component('volume-surge-bt-page', {
    template: '#volume-surge-bt-tpl',
    setup() {
        const vsStockCode = ref('600519');
        const vsLookback = ref(6);
        const vsHoldDays = ref(10);
        const vsVolMin = ref(1.5);
        const vsVolMax = ref(4.0);
        const vsShrinkDays = ref(3);
        const vsSingleLoading = ref(false);
        const vsSingleResult = ref({ trades: [], summary: {} });

        const vsMktLookback = ref(6);
        const vsMktHoldDays = ref(10);
        const vsMktLoading = ref(false);
        const vsMktResult = ref({ trades: [], summary: {} });

        async function runSingleBt() {
            if (!vsStockCode.value) return;
            vsSingleLoading.value = true;
            vsSingleResult.value = { trades: [], summary: {} };
            try {
                const params = new URLSearchParams({
                    stock_code: vsStockCode.value,
                    lookback_months: vsLookback.value,
                    hold_days: vsHoldDays.value,
                    volume_ratio_min: vsVolMin.value,
                    volume_ratio_max: vsVolMax.value,
                    shrink_days: vsShrinkDays.value,
                });
                const r = await fetch(`${API_BASE}/backtest/volume-surge?${params}`);
                const data = await r.json();
                if (data.error) { vsSingleResult.value = { trades: [], summary: {} }; }
                else vsSingleResult.value = data;
            } catch (e) {
                console.error(e);
            } finally {
                vsSingleLoading.value = false;
            }
        }

        async function runMarketBt() {
            vsMktLoading.value = true;
            vsMktResult.value = { trades: [], summary: {} };
            try {
                const params = new URLSearchParams({
                    lookback_months: vsMktLookback.value,
                    hold_days: vsMktHoldDays.value,
                    volume_ratio_min: vsVolMin.value,
                    volume_ratio_max: vsVolMax.value,
                    shrink_days: vsShrinkDays.value,
                });
                const r = await fetch(`${API_BASE}/backtest/volume-surge/market?${params}`);
                const data = await r.json();
                if (data.error) { vsMktResult.value = { trades: [], summary: {} }; }
                else vsMktResult.value = data;
            } catch (e) {
                console.error(e);
            } finally {
                vsMktLoading.value = false;
            }
        }

        return {
            vsStockCode, vsLookback, vsHoldDays, vsVolMin, vsVolMax, vsShrinkDays,
            vsSingleLoading, vsSingleResult, runSingleBt,
            vsMktLookback, vsMktHoldDays, vsMktLoading, vsMktResult, runMarketBt,
            fmt, fmtGrowth, valClass,
        };
    },
});

app.component('quant-breakout-bt-page', {
    template: '#quant-breakout-bt-tpl',
    setup() {
        const qTab = ref('single');
        const qStockCode = ref('002421');
        const qNDays = ref(20);
        const today = new Date();
        const qEndDate = ref(today.toISOString().split('T')[0]);
        const qStartDate = ref(new Date(today.getFullYear() - 2, 0, 1).toISOString().split('T')[0]);
        const qLoading = ref(false);
        const qResult = ref({});
        const qError = ref('');

        const mktMonths = ref(6);
        const mktLoading = ref(false);
        const mktResult = ref({});
        const mktError = ref('');

        async function runQbt() {
            if (!qStockCode.value || !qStartDate.value || !qEndDate.value) return;
            qLoading.value = true;
            qResult.value = {};
            qError.value = '';
            try {
                const params = new URLSearchParams({
                    stock_code: qStockCode.value,
                    n_days: qNDays.value,
                    start_date: qStartDate.value,
                    end_date: qEndDate.value,
                });
                const r = await fetch(`${API_BASE}/backtest/quantitative-breakout?${params}`);
                const data = await r.json();
                if (data.error) qError.value = data.error;
                else qResult.value = data;
            } catch (e) {
                qError.value = '请求失败: ' + e.message;
            } finally {
                qLoading.value = false;
            }
        }

        async function runMktBt() {
            mktLoading.value = true;
            mktResult.value = {};
            mktError.value = '';
            try {
                const params = new URLSearchParams({
                    months: mktMonths.value,
                });
                const r = await fetch(`${API_BASE}/backtest/quantitative-breakout/market?${params}`);
                if (!r.ok) throw new Error('查询失败');
                const data = await r.json();
                if (data.error) mktError.value = data.error;
                else mktResult.value = data;
            } catch (e) {
                mktError.value = '请求失败: ' + e.message;
            } finally {
                mktLoading.value = false;
            }
        }

        return {
            qTab, qStockCode, qNDays, qStartDate, qEndDate,
            qLoading, qResult, qError, runQbt,
            mktMonths, mktLoading, mktResult, mktError, runMktBt,
            fmt, fmtGrowth, valClass,
        };
    },
});

// ── Profile Page ──
app.component('profile-page', {
    template: '#profile-tpl',
    setup() {
        const activeTab = ref('single');

        // ── Tab1: 单股画像 ──
        const stockCode = ref('600519');
        const loading = ref(false);
        const profile = ref(null);
        const error = ref('');
        const finChartLoading = ref(false);
        const finChartCanvas = ref(null);
        const fundChartLoading = ref(false);
        const fundChartImg = ref('');
        const fundChartImgEl = ref(null);
        const divChartCanvas = ref(null);

        let divChartGeo = null;
        function loadDivChart() {
            const c = divChartCanvas.value;
            const div = profile.value && profile.value.dividend;
            if (!c || !div || !div.trend || !div.trend.length) return;
            const p = c.parentElement, ctx = c.getContext('2d');
            const W = p.clientWidth, H = p.clientHeight, pr = window.devicePixelRatio || 1;
            c.width = W * pr; c.height = H * pr; c.style.width = W + 'px'; c.style.height = H + 'px';
            ctx.scale(pr, pr);
            const pad = { top: 12, bottom: 26, left: 44, right: 68 };
            const cw = W - pad.left - pad.right, ch = H - pad.top - pad.bottom;
            const n = div.trend.length;
            const xs = div.trend.map((_, i) => pad.left + cw * (n === 1 ? 0.5 : i / (n - 1)));
            const cashMax = Math.max(...div.trend.map(t => t.cash_per_share || 0)) * 1.15 || 1;
            const ylds = div.trend.map(t => t.dividend_yield).filter(v => v != null);
            const yldMax = (ylds.length ? Math.max(...ylds) : 0) * 1.2 || 1;
            const prs = div.trend.map(t => t.payout_ratio).filter(v => v != null);
            const prMax = (prs.length ? Math.max(...prs) : 0) * 1.2 || 1;
            const barW = Math.min(28, cw / n * 0.55);
            function yc(v) { return pad.top + ch * (1 - v / cashMax); }
            function yy(v) { return pad.top + ch * (1 - v / yldMax); }
            function yp(v) { return pad.top + ch * (1 - v / prMax); }
            divChartGeo = { ctx, W, H, pad, cw, ch, xs, cashMax, yldMax, prMax, barW, yc, yy, yp, trend: div.trend };

            function draw() {
                ctx.clearRect(0, 0, W, H);
                ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 1;
                for (let i = 0; i <= 4; i++) {
                    const y = pad.top + ch * i / 4;
                    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + cw, y); ctx.stroke();
                }
                div.trend.forEach((t, i) => {
                    const x = xs[i], bh = ch * (t.cash_per_share || 0) / cashMax;
                    ctx.fillStyle = 'rgba(100,149,237,0.7)';
                    ctx.fillRect(x - barW / 2, pad.top + ch - bh, barW, bh);
                });
                ctx.beginPath(); ctx.strokeStyle = '#ffd700'; ctx.lineWidth = 2;
                let started = false;
                div.trend.forEach((t, i) => {
                    if (t.dividend_yield == null) return;
                    const y = yy(t.dividend_yield);
                    started ? ctx.lineTo(xs[i], y) : (ctx.moveTo(xs[i], y), started = true);
                });
                ctx.stroke();
                ctx.fillStyle = '#ffd700';
                div.trend.forEach((t, i) => {
                    if (t.dividend_yield == null) return;
                    ctx.beginPath(); ctx.arc(xs[i], yy(t.dividend_yield), 2.5, 0, Math.PI * 2); ctx.fill();
                });
                ctx.beginPath(); ctx.strokeStyle = '#4ecdc4'; ctx.lineWidth = 2;
                let pstarted = false;
                div.trend.forEach((t, i) => {
                    if (t.payout_ratio == null) return;
                    const y = yp(t.payout_ratio);
                    pstarted ? ctx.lineTo(xs[i], y) : (ctx.moveTo(xs[i], y), pstarted = true);
                });
                ctx.stroke();
                ctx.fillStyle = '#4ecdc4';
                div.trend.forEach((t, i) => {
                    if (t.payout_ratio == null) return;
                    ctx.beginPath(); ctx.arc(xs[i], yp(t.payout_ratio), 2.5, 0, Math.PI * 2); ctx.fill();
                });
                ctx.fillStyle = '#ccc'; ctx.font = '10px sans-serif'; ctx.textAlign = 'right';
                for (let i = 0; i <= 4; i++) {
                    ctx.fillText((cashMax * i / 4).toFixed(1), pad.left - 6, pad.top + ch * (1 - i / 4) + 3);
                }
                ctx.textAlign = 'left'; ctx.fillStyle = '#86f7dc';
                for (let i = 0; i <= 4; i++) {
                    ctx.fillText((yldMax * i / 4).toFixed(1) + '%', pad.left + cw + 6, pad.top + ch * (1 - i / 4) + 3);
                }
                ctx.fillStyle = '#4ecdc4'; ctx.textAlign = 'left';
                ctx.fillText('派息率%', pad.left + cw + 6, pad.top + 4);
                ctx.fillText(prMax.toFixed(0) + '%', pad.left + cw + 6, pad.top + ch + 12);
                ctx.fillStyle = '#e2e8f0'; ctx.font = '11px sans-serif'; ctx.textAlign = 'center';
                div.trend.forEach((t, i) => {
                    ctx.fillText(t.year, xs[i], H - pad.bottom + 14);
                    if (t.times > 1) ctx.fillText('×' + t.times, xs[i], pad.top + 8);
                });
            }

            function onMove(ev) {
                const rect = c.getBoundingClientRect();
                const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
                const g = divChartGeo;
                let idx = -1, best = 1e9;
                g.xs.forEach((x, i) => { const d = Math.abs(mx - x); if (d < best) { best = d; idx = i; } });
                if (idx < 0 || best > g.barW) { draw(); return; }
                const t = g.trend[idx];
                const x = g.xs[idx], bh = g.ch * (t.cash_per_share || 0) / g.cashMax;
                const barTop = g.pad.top + g.ch - bh;
                if (my < barTop - 4 || my > g.pad.top + g.ch) { draw(); return; }
                draw();
                ctx.fillStyle = 'rgba(100,149,237,0.95)';
                ctx.fillRect(x - barW / 2, barTop, barW, bh);
                const lines = [
                    `${t.year}年 每股派息：${t.cash_per_share != null ? t.cash_per_share.toFixed(2) : '-'}元`,
                    t.dividend_yield != null ? `股息率：${t.dividend_yield.toFixed(2)}%` : '股息率：-',
                    t.payout_ratio != null ? `派息率：${t.payout_ratio.toFixed(1)}%` : '派息率：-',
                    `分红次数：${t.times}次`,
                ];
                const tw = Math.max(...lines.map(l => ctx.measureText(l).width)) + 16;
                const th = lines.length * 16 + 10;
                const tx = Math.min(Math.max(x - tw / 2, 4), W - tw - 4);
                const ty = Math.max(barTop - th - 8, 4);
                ctx.fillStyle = 'rgba(20,20,35,0.92)';
                ctx.strokeStyle = 'rgba(100,149,237,0.6)';
                ctx.beginPath(); ctx.roundRect(tx, ty, tw, th, 4); ctx.fill(); ctx.stroke();
                ctx.fillStyle = '#fff'; ctx.font = '11px sans-serif'; ctx.textAlign = 'left';
                lines.forEach((l, i) => ctx.fillText(l, tx + 8, ty + 16 + i * 16));
            }

            c.onmousemove = onMove;
            c.onmouseleave = () => draw();
            draw();
        }


        async function loadProfile() {
            if (!stockCode.value) return;
            loading.value = true;
            error.value = '';
            profile.value = null;
            try {
                    const r = await fetch(`${API_BASE}/profile/${stockCode.value}?refresh=true`);
                const data = await r.json();
                if (data.error) error.value = data.error;
                else {
                    profile.value = data;
                    loadFinChart();
                    loadFundChart();
                    loadZxmTags();
                    checkWatchlist();
                    nextTick(loadDivChart);
                }
            } catch (e) {
                error.value = '请求失败: ' + e.message;
            } finally {
                loading.value = false;
            }
        }

        function scoreClass(val) {
            if (val == null) return '';
            if (val >= 70) return 'score-high';
            if (val >= 40) return 'score-mid';
            return 'score-low';
        }

        function scoreTextClass(val) {
            if (val == null) return '';
            if (val >= 70) return 'up';
            if (val >= 40) return '';
            return 'down';
        }

        function rsiClass(val) {
            if (val == null) return '';
            if (val > 70) return 'down';
            if (val < 30) return 'up';
            return '';
        }

        function debtClass(val) {
            if (val == null) return '';
            if (val > 60) return 'down';
            return 'up';
        }

        function gmTrendClass(item, idx, trend) {
            if (idx === 0 || item.rate == null) return '';
            const prev = trend[idx - 1];
            return prev.rate != null && item.rate >= prev.rate ? 'up' : 'down';
        }

        function introStatusName(status) {
            return { unchanged: '定位未变', transforming: '转型中', diversifying: '跨界延伸', pivoting: '战略转向', unknown: '定位待补充' }[status] || '定位待补充';
        }

        function chainName(position) {
            return { upstream: '上游', midstream: '中游', downstream: '下游' }[position] || position;
        }

        const zxmTags = ref(null);
        const zxmLoading = ref(false);

        async function loadZxmTags() {
            if (!stockCode.value) return;
            zxmLoading.value = true;
            try {
                const r = await fetch(`${API_BASE}/profile/${stockCode.value}/zxm-tags`);
                const data = await r.json();
                if (!data.error) zxmTags.value = data;
            } catch (e) {} finally {
                zxmLoading.value = false;
            }
        }

        function zxmClass(val) {
            const good = ['造血型', '经营主导型', '现金充裕', '轻资产', '零杠杆', '低杠杆', '高毛利', '盈利', '价值创造型', '产能高效', '强转化', '中转化', '现金实现强', '现金奶牛', '爆发增长', '高速增长', '稳健增长', '增收增利', '优秀', '良好', 'FCF充裕', '存货风险低', '合同负债高', '合同负债正常', '现金正常'];
            const bad = ['输血型', '投资主导型', '现金紧张', '重资产', '高杠杆', '低毛利', '亏损', '会计调整型', '产能低效', '极弱转化', '现金实现弱', '纸面富贵', '失血状态', '衰退', '减收减利', '差', '中下', 'FCF为负', '存货风险高', '增收不增利'];
            if (good.includes(val)) return 'up';
            if (bad.includes(val)) return 'down';
            return '';
        }

        async function loadFinChart() {
            if (!stockCode.value) return;
            finChartLoading.value = true;
            try {
                const r = await fetch(`${API_BASE}/profile/${stockCode.value}/fin-chart`);
                const data = await r.json();
                if (data.years && data.years.length) renderFinChart(data);
            } catch (e) {}
            finally { finChartLoading.value = false; }
        }

        function renderFinChart(data) {
            const canvas = finChartCanvas.value;
            if (!canvas) return;
            const parent = canvas.parentElement;
            const rect = parent.getBoundingClientRect();

            let tooltip = parent.querySelector('.chart-tooltip');
            if (!tooltip) {
                tooltip = document.createElement('div');
                tooltip.className = 'chart-tooltip';
                tooltip.style.cssText = 'position:absolute;display:none;background:rgba(20,20,40,0.92);border:1px solid #333;border-radius:6px;padding:10px 14px;font-size:12px;color:#ccc;pointer-events:none;z-index:100;white-space:nowrap;line-height:1.7;';
                parent.style.position = 'relative';
                parent.appendChild(tooltip);
            }

            const dpr = window.devicePixelRatio || 1;
            canvas.width = rect.width * dpr;
            canvas.height = rect.height * dpr;
            canvas.style.width = rect.width + 'px';
            canvas.style.height = rect.height + 'px';
            const ctx = canvas.getContext('2d');
            const W = canvas.width, H = canvas.height;
            const pad = { top: 32*dpr, bottom: 32*dpr, left: 58*dpr, right: 58*dpr };
            const cw = W - pad.left - pad.right, ch = H - pad.top - pad.bottom;

            ctx.clearRect(0, 0, W, H);

            const n = data.years.length;

            const rMax = Math.max(...data.revenues) * 1.15;
            const pMin = Math.min(...data.profits) * 1.1;
            const pMax = Math.max(...data.profits) * 1.15;
            const pRange = pMax - pMin || 1;
            const gVals = data.growth_rates.filter(v => v != null);
            const gMin = Math.min(...gVals) * 1.1;
            const gMax = Math.max(...gVals) * 1.15;
            const gRange = gMax - gMin || 1;

            const wk = data.weekly_kline || [];
            let priceMax = 0;
            for (const bar of wk) {
                if (bar.high > priceMax) priceMax = bar.high;
            }
            priceMax *= 1.15;

            function yRev(v) { return pad.top + ch * (1 - v / rMax); }
            function yProf(v) { return pad.top + ch * (1 - (v - pMin) / pRange); }
            function yGr(v) { return pad.top + ch * (1 - (v - gMin) / gRange); }
            function yPrice(v) { return pad.top + ch * (1 - v / priceMax); }

            const yearStart = data.years[0];
            const yearEnd = data.years[n - 1];
            const wkFirst = wk.length ? new Date(wk[0].date).getTime() : null;
            const wkLast = wk.length ? new Date(wk[wk.length - 1].date).getTime() : null;
            const msStart = Math.min(new Date(yearStart, 0, 1).getTime(), wkFirst != null ? wkFirst : Infinity);
            const msEnd = Math.max(new Date(yearEnd, 11, 31).getTime(), wkLast != null ? wkLast : -Infinity);
            const msRange = msEnd - msStart || 1;

            function dateToX(dateStr) {
                const t = new Date(dateStr).getTime();
                return pad.left + cw * (t - msStart) / msRange;
            }
            const xs = data.years.map(y => dateToX(new Date(y, 6, 1)));

            ctx.strokeStyle = 'rgba(255,255,255,0.05)';
            ctx.lineWidth = 1*dpr;
            for (let i = 0; i <= 4; i++) {
                const y = pad.top + ch * i / 4;
                ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + cw, y); ctx.stroke();
            }

            for (let i = 0; i < n; i++) {
                const x = xs[i] - 14*dpr, w = 28*dpr;
                const h = ch * data.revenues[i] / rMax;
                ctx.fillStyle = 'rgba(100,149,237,0.45)';
                ctx.fillRect(x, pad.top + ch - h, w, h);
            }

            ctx.beginPath();
            ctx.strokeStyle = '#ffd700'; ctx.lineWidth = 2.5*dpr;
            for (let i = 0; i < n; i++) {
                const y = yProf(data.profits[i]);
                i === 0 ? ctx.moveTo(xs[i], y) : ctx.lineTo(xs[i], y);
            }
            ctx.stroke();
            ctx.fillStyle = '#ffd700';
            for (let i = 0; i < n; i++) {
                const y = yProf(data.profits[i]);
                ctx.beginPath(); ctx.arc(xs[i], y, 3.5*dpr, 0, Math.PI*2); ctx.fill();
            }

            ctx.beginPath();
            ctx.setLineDash([6*dpr, 3*dpr]);
            ctx.strokeStyle = '#ff6b6b'; ctx.lineWidth = 2*dpr;
            for (let i = 0; i < n; i++) {
                const v = data.growth_rates[i];
                if (v == null) continue;
                const y = yGr(v);
                i === 0 || data.growth_rates[i-1] == null ? ctx.moveTo(xs[i], y) : ctx.lineTo(xs[i], y);
            }
            ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle = '#ff6b6b';
            for (let i = 0; i < n; i++) {
                const v = data.growth_rates[i];
                if (v == null) continue;
                ctx.beginPath(); ctx.arc(xs[i], yGr(v), 3*dpr, 0, Math.PI*2); ctx.fill();
            }

            if (wk.length > 0) {
                const candleW = Math.max(1, Math.min(6, cw / wk.length * 0.6)) * dpr;
                for (const bar of wk) {
                    const x = dateToX(bar.date);
                    const yO = yPrice(bar.open), yC = yPrice(bar.close);
                    const yH = yPrice(bar.high), yL = yPrice(bar.low);
                    const up = bar.close >= bar.open;
                    ctx.strokeStyle = up ? '#ef4444' : '#10b981';
                    ctx.lineWidth = 1 * dpr;
                    ctx.beginPath(); ctx.moveTo(x, yH); ctx.lineTo(x, yL); ctx.stroke();
                    const bodyTop = Math.min(yO, yC);
                    const bodyH = Math.max(Math.abs(yO - yC), 1 * dpr);
                    ctx.fillStyle = up ? '#ef4444' : '#10b981';
                    ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyH);
                }
            }

            ctx.fillStyle = '#666'; ctx.font = `${10*dpr}px sans-serif`; ctx.textAlign = 'right';
            for (let i = 0; i <= 4; i++) {
                const v = Math.round(rMax * i / 4);
                ctx.fillText(v + '亿', pad.left - 6*dpr, pad.top + ch * (1 - i/4) + 4*dpr);
            }

            ctx.textAlign = 'left';
            ctx.fillStyle = '#4ecdc4';
            for (let i = 0; i <= 4; i++) {
                const v = Math.round(priceMax * i / 4);
                ctx.fillText(v + '元', pad.left + cw + 6*dpr, pad.top + ch * (1 - i/4) + 4*dpr);
            }

            ctx.fillStyle = '#999'; ctx.font = `${11*dpr}px sans-serif`; ctx.textAlign = 'center';
            for (let i = 0; i < n; i++) {
                ctx.fillText(data.years[i], xs[i], H - pad.bottom + 16*dpr);
            }

            const legend = [
                {label:'营收(亿)',color:'rgba(100,149,237,0.7)'},{label:'净利润(亿)',color:'#ffd700'},
                {label:'净利增长率%',color:'#ff6b6b'},{label:'周K',color:'#4ecdc4'},
            ];
            ctx.font = `${11*dpr}px sans-serif`; ctx.textAlign = 'left';
            let lx = pad.left;
            for (const item of legend) {
                ctx.fillStyle = item.color;
                ctx.fillRect(lx, 8*dpr, 12*dpr, 12*dpr);
                ctx.fillStyle = '#ccc';
                ctx.fillText(item.label, lx + 16*dpr, 19*dpr);
                lx += ctx.measureText(item.label).width + 28*dpr;
            }

            const chartData = { data, xs, pad, cw, n, yProf, yGr, rMax, wk, dateToX, yPrice, candleW: Math.max(1, Math.min(6, cw / wk.length * 0.6)) * dpr };
            canvas.chartData = chartData;

            canvas.onmousemove = function(e) {
                const cr = canvas.getBoundingClientRect();
                const mx = (e.clientX - cr.left) * dpr;
                const cd = canvas.chartData;
                if (!cd) return;

                let idx = -1, minDist = Infinity;
                for (let i = 0; i < cd.n; i++) {
                    const dist = Math.abs(mx - cd.xs[i]);
                    if (dist < minDist) { minDist = dist; idx = i; }
                }
                if (idx < 0 || minDist > cw / cd.n * 1.2) { tooltip.style.display = 'none'; return; }

                const d = cd.data;
                const yr = d.years[idx];
                const rev = d.revenues[idx];
                const prof = d.profits[idx];
                const gr = d.growth_rates[idx];

                let html = `<div style="color:#ffd700;font-weight:700;margin-bottom:4px;">${yr}年</div>`;
                    html += `<div><span style="color:#6495ed;">营收</span> ${rev.toFixed(1)}亿</div>`;
                    html += `<div><span style="color:#ffd700;">净利润</span> ${prof.toFixed(2)}亿</div>`;
                    html += `<div><span style="color:#ff6b6b;">净利增长率</span> ${gr != null ? (gr >= 0 ? '+' : '') + gr.toFixed(1) + '%' : 'N/A'}</div>`;

                if (cd.wk.length > 0) {
                    const yrBars = cd.wk.filter(b => b.date.startsWith(String(yr)));
                    if (yrBars.length > 0) {
                        const last = yrBars[yrBars.length - 1];
                        html += `<div style="margin-top:2px;padding-top:2px;border-top:1px solid #333;">`;
                        html += `<span style="color:#4ecdc4;">年末周K</span></div>`;
                        html += `<div>开 <b>${last.open.toFixed(2)}</b> 高 <b>${last.high.toFixed(2)}</b></div>`;
                        html += `<div>低 <b>${last.low.toFixed(2)}</b> 收 <b>${last.close.toFixed(2)}</b></div>`;
                    }
                }

                tooltip.innerHTML = html;
                const tx = e.clientX - cr.left + 15;
                const ty = e.clientY - cr.top - 10;
                const tw = tooltip.offsetWidth || 180;
                const th = tooltip.offsetHeight || 100;
                tooltip.style.left = (tx + tw > cr.width ? tx - tw - 30 : tx) + 'px';
                tooltip.style.top = (ty + th > cr.height ? cr.height - th - 5 : (ty < 0 ? 5 : ty)) + 'px';
                tooltip.style.display = 'block';
            };
            canvas.onmouseout = function() { tooltip.style.display = 'none'; };
        }

        async function loadFundChart() {
            if (!stockCode.value) return;
            fundChartLoading.value = true;
            try {
                const ts = Date.now();
                fundChartImg.value = `${API_BASE}/profile/${stockCode.value}/fund-chart-img?t=${ts}`;
            } catch (e) {}
            finally { fundChartLoading.value = false; }
        }

        function renderFundChart(series) {
            const canvas = fundChartCanvas.value;
            if (!canvas) return;
            const parent = canvas.parentElement;
            const rect = parent.getBoundingClientRect();

            let tooltip = parent.querySelector('.chart-tooltip');
            if (!tooltip) {
                tooltip = document.createElement('div');
                tooltip.className = 'chart-tooltip';
                tooltip.style.cssText = 'position:absolute;display:none;background:rgba(20,20,40,0.92);border:1px solid #333;border-radius:6px;padding:10px 14px;font-size:12px;color:#ccc;pointer-events:none;z-index:100;white-space:nowrap;line-height:1.7;';
                parent.style.position = 'relative';
                parent.appendChild(tooltip);
            }

            const dpr = window.devicePixelRatio || 1;
            canvas.width = rect.width * dpr;
            canvas.height = rect.height * dpr;
            canvas.style.width = rect.width + 'px';
            canvas.style.height = rect.height + 'px';
            const ctx = canvas.getContext('2d');
            const W = canvas.width, H = canvas.height;
            const pad = { top: 30*dpr, bottom: 30*dpr, left: 104*dpr, right: 58*dpr };
            const cw = W - pad.left - pad.right, ch = H - pad.top - pad.bottom;
            const n = series.length;

            ctx.clearRect(0, 0, W, H);

            const aVals = series.map(s => (s.total_amount || 0) / 1e8);
            const fVals = series.map(s => s.fund_count || 0);
            const cVals = series.map(s => s.close_price || 0);
            const hVals = series.map(s => s.intra_high || 0);
            const aMax = Math.max(...aVals) * 1.15 || 1;
            const fMax = Math.max(...fVals) * 1.15 || 1;
            const pMax = Math.max(...hVals, ...cVals) * 1.15 || 1;

            function yAmt(v) { return pad.top + ch * (1 - v / aMax); }
            function yFund(v) { return pad.top + ch * (1 - v / fMax); }
            function yPrice(v) { return pad.top + ch * (1 - v / pMax); }

            const xStep = n > 1 ? cw / (n - 1) : cw;
            const xs = series.map((_, i) => pad.left + i * xStep);

            ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 1*dpr;
            for (let i = 0; i <= 4; i++) {
                const y = pad.top + ch * i / 4;
                ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + cw, y); ctx.stroke();
            }

            const barW = Math.max(1, Math.min(9, cw / n * 0.55)) * dpr;
            for (let i = 0; i < n; i++) {
                const x = xs[i];
                const h = ch * aVals[i] / aMax;
                ctx.fillStyle = series[i].report_type === 'F' ? 'rgba(59,130,246,0.6)' : 'rgba(59,130,246,0.25)';
                ctx.fillRect(x - barW/2, pad.top + ch - h, barW, h);
            }

            ctx.beginPath();
            ctx.strokeStyle = '#ef4444'; ctx.lineWidth = 2*dpr;
            for (let i = 0; i < n; i++) {
                const y = yPrice(cVals[i]);
                i === 0 ? ctx.moveTo(xs[i], y) : ctx.lineTo(xs[i], y);
            }
            ctx.stroke();
            ctx.fillStyle = '#ef4444';
            for (let i = 0; i < n; i++) {
                const y = yPrice(cVals[i]);
                ctx.beginPath(); ctx.arc(xs[i], y, 2.5*dpr, 0, Math.PI*2); ctx.fill();
            }

            ctx.fillStyle = '#f59e0b';
            for (let i = 0; i < n; i++) {
                const x = xs[i], y = yPrice(hVals[i]);
                ctx.beginPath(); ctx.moveTo(x, y - 6*dpr); ctx.lineTo(x - 5*dpr, y + 5*dpr); ctx.lineTo(x + 5*dpr, y + 5*dpr); ctx.closePath(); ctx.fill();
            }
            let peakIdx = 0, peakVal = -Infinity;
            series.forEach((s, i) => { if ((s.intra_high || 0) > peakVal) { peakVal = s.intra_high; peakIdx = i; } });
            ctx.fillStyle = '#f59e0b'; ctx.font = `bold ${11*dpr}px sans-serif`; ctx.textAlign = 'center';
            ctx.fillText('高点 ' + peakVal.toFixed(2), xs[peakIdx], yPrice(peakVal) - 10*dpr);

            let segStart = 0;
            for (let i = 1; i <= n; i++) {
                if (i < n && series[i].report_type === series[segStart].report_type) continue;
                const isQ = series[segStart].report_type === 'Q';
                ctx.beginPath();
                ctx.setLineDash(isQ ? [6*dpr, 3*dpr] : []);
                ctx.strokeStyle = '#ff69b4'; ctx.lineWidth = 2*dpr;
                for (let j = segStart; j < i; j++) {
                    const y = yFund(fVals[j]);
                    j === segStart ? ctx.moveTo(xs[j], y) : ctx.lineTo(xs[j], y);
                }
                ctx.stroke();
                segStart = i;
            }
            ctx.setLineDash([]);
            ctx.fillStyle = '#ff69b4';
            for (let i = 0; i < n; i++) {
                const y = yFund(fVals[i]);
                ctx.beginPath(); ctx.arc(xs[i], y, 2.5*dpr, 0, Math.PI*2); ctx.fill();
            }

            ctx.fillStyle = '#ff69b4'; ctx.font = `${10*dpr}px sans-serif`; ctx.textAlign = 'right';
            for (let i = 0; i <= 4; i++) {
                const v = Math.round(fMax * i / 4);
                ctx.fillText(v + '家', pad.left - 8*dpr, pad.top + ch*(1 - i/4) + 4*dpr);
            }
            ctx.fillStyle = '#3b82f6';
            for (let i = 0; i <= 4; i++) {
                const v = (aMax * i / 4).toFixed(1);
                ctx.fillText(v + '亿股', pad.left - 56*dpr, pad.top + ch*(1 - i/4) + 4*dpr);
            }
            ctx.textAlign = 'left';
            ctx.fillStyle = '#ef4444';
            for (let i = 0; i <= 4; i++) {
                const v = Math.round(pMax * i / 4);
                ctx.fillText(v + '元', pad.left + cw + 6*dpr, pad.top + ch*(1 - i/4) + 4*dpr);
            }

            ctx.fillStyle = '#999'; ctx.font = `${10*dpr}px sans-serif`; ctx.textAlign = 'center';
            for (let i = 0; i < n; i += Math.max(1, Math.ceil(n / 12))) {
                ctx.fillText(series[i].quarter, xs[i], H - pad.bottom + 16*dpr);
            }

            const legend = [
                {label:'季末收盘价(元)', color:'#ef4444'},
                {label:'季内盘中最高', color:'#f59e0b'},
                {label:'持仓基金家数(实线=半年/年报,虚线=季报)', color:'#ff69b4'},
                {label:'基金持股量(亿股)', color:'#3b82f6'},
            ];
            ctx.font = `${11*dpr}px sans-serif`; ctx.textAlign = 'left';
            let lx = pad.left;
            for (const item of legend) {
                ctx.fillStyle = item.color;
                ctx.fillRect(lx, 8*dpr, 12*dpr, 12*dpr);
                ctx.fillStyle = '#ccc';
                ctx.fillText(item.label, lx + 16*dpr, 19*dpr);
                lx += ctx.measureText(item.label).width + 28*dpr;
            }

            canvas.chartData = { series, xs, pad, cw, n, yPrice, yFund };
            canvas.onmousemove = function(e) {
                const cr = canvas.getBoundingClientRect();
                const mx = (e.clientX - cr.left) * dpr;
                const cd = canvas.chartData;
                if (!cd) return;
                let idx = -1, minDist = Infinity;
                for (let i = 0; i < cd.n; i++) {
                    const dist = Math.abs(mx - cd.xs[i]);
                    if (dist < minDist) { minDist = dist; idx = i; }
                }
                if (idx < 0 || minDist > cd.cw / cd.n * 1.2) { tooltip.style.display = 'none'; return; }
                const s = cd.series[idx];
                const aYi = (s.total_amount || 0) / 1e8;
                const isQ = s.report_type === 'Q';
                let html = `<div style="color:#ff69b4;font-weight:700;margin-bottom:4px;">${s.quarter} ${isQ ? '（季报·前十大）' : '（半年/年报·全部）'}</div>`;
                html += `<div><span style="color:#ef4444;">季末收盘</span> ${s.close_price.toFixed(2)}元 · <span style="color:#f59e0b;">盘中最高</span> ${s.intra_high.toFixed(2)}元</div>`;
                html += `<div><span style="color:#ff69b4;">持仓基金</span> ${s.fund_count}家（主动 ${s.active_count} / 被动 ${s.passive_count}）</div>`;
                html += `<div><span style="color:#3b82f6;">基金持股量</span> ${aYi.toFixed(2)}亿股 · 市值 ${(s.total_mkv / 1e8).toFixed(0)}亿</div>`;
                tooltip.innerHTML = html;
                const tx = e.clientX - cr.left + 15;
                const ty = e.clientY - cr.top - 10;
                const tw = tooltip.offsetWidth || 180;
                const th = tooltip.offsetHeight || 100;
                tooltip.style.left = (tx + tw > cr.width ? tx - tw - 30 : tx) + 'px';
                tooltip.style.top = (ty + th > cr.height ? cr.height - th - 5 : (ty < 0 ? 5 : ty)) + 'px';
                tooltip.style.display = 'block';
            };
            canvas.onmouseout = function() { tooltip.style.display = 'none'; };
        }

        function goToProfile(code) {
            stockCode.value = code;
            if (activeTab.value === 'watchlist' && watchlistData.value) {
                setNavList(watchlistData.value.rows);
            } else if (activeTab.value === 'screening' && searchResult.value) {
                setNavList(searchResult.value.rows);
            }
            activeTab.value = 'single';
            loadProfile();
        }

        const navList = ref(null);
        const navTotal = computed(() => navList.value ? navList.value.length : 0);

        function setNavList(rows) {
            navList.value = rows || [];
        }

        const currentIdx = computed(() => {
            const list = navList.value;
            if (!list || list.length === 0) return -1;
            return list.findIndex(r => r.stock_code === stockCode.value);
        });
        const hasPrev = computed(() => currentIdx.value > 0);
        const hasNext = computed(() => {
            const list = navList.value;
            return list && currentIdx.value >= 0 && currentIdx.value < list.length - 1;
        });

        function goPrev() {
            const list = navList.value;
            const idx = currentIdx.value;
            if (list && idx > 0) goToProfile(list[idx - 1].stock_code);
        }
        function goNext() {
            const list = navList.value;
            const idx = currentIdx.value;
            if (list && idx >= 0 && idx < list.length - 1) goToProfile(list[idx + 1].stock_code);
        }

        function onKeydown(e) {
            if (activeTab.value !== 'single' || !profile.value) return;
            if (e.key === 'ArrowLeft') { e.preventDefault(); goPrev(); }
            if (e.key === 'ArrowRight') { e.preventDefault(); goNext(); }
        }

        // ── Tab2: 画像筛选 ──
        const stageOptions = [
            { id: 'stage.s2', label: 'S2 突围加速' },
            { id: 'stage.s1s2', label: 'S1S2 过渡' },
            { id: 'stage.s1', label: 'S1 打底' },
            { id: 'stage.s3', label: 'S3 见顶' },
            { id: 'stage.s4', label: 'S4 衰败' },
        ];
        const selectedStages = ref([]);
        const filterTechScore = ref(0);
        const filterFundScore = ref(0);
        const filterRevGrowth = ref(null);
        const filterProfitGrowth = ref(null);
        const filterPrevYearProfitMin = ref(null);
        const filterPrevYearProfitMax = ref(null);
        const filterCurQuarterProfitMin = ref(null);
        const filterCurQuarterProfitMax = ref(null);
        const filterDebtMax = ref(null);
        const filterGmGrowthQ = ref(null);
        const filterGmGrowth2y = ref(null);
        const filterContractLiabMin = ref(null);
        const filterContractLiabMax = ref(null);
        const filterRoeMin = ref(null);
        const filterRoeMax = ref(null);
        const filterNetMarginMin = ref(null);
        const filterNetMarginMax = ref(null);
        const filterMarketCapRange = ref('');
        const marketCapRanges = [
            { label: '50亿以下', min: 0, max: 50 },
            { label: '50~100亿', min: 50, max: 100 },
            { label: '100~200亿', min: 100, max: 200 },
            { label: '200~300亿', min: 200, max: 300 },
            { label: '300~500亿', min: 300, max: 500 },
            { label: '500~1000亿', min: 500, max: 1000 },
            { label: '1000~5000亿', min: 1000, max: 5000 },
            { label: '5000~10000亿', min: 5000, max: 10000 },
            { label: '1万亿以上', min: 10000, max: null },
        ];
        const filterRoeTtmMin = ref(null);
const filterRoeTtmMax = ref(null);
const filterPeMax = ref(null);
const filterPegMax = ref(null);
        const filterDividendYieldMin = ref(null);
        const filterDividendYieldMax = ref(null);
        const filterHasDivThisYear = ref(false);
        const filterHasMidYear = ref(false);
        const filterConsecutiveDivYears = ref(null);
        const filterRevCagr3yMin = ref(null);
        const filterRevCagr3yMax = ref(null);
        const filterRevCagr5yMin = ref(null);
        const filterRevCagr5yMax = ref(null);
        const filterProfitCagr3yMin = ref(null);
        const filterProfitCagr3yMax = ref(null);
        const filterProfitCagr5yMin = ref(null);
        const filterProfitCagr5yMax = ref(null);

        const inWatchlist = ref(false);
        const watchlistLoading = ref(false);
        const watchlistData = ref(null);
        const watchlistCount = ref(0);

        const stockSuggestions = ref([]);
        const stockSuggestionIdx = ref(-1);
        let searchTimer = null;

        async function onStockInput() {
            const q = stockCode.value.trim();
            if (q.length < 1) { stockSuggestions.value = []; return; }
            if (searchTimer) clearTimeout(searchTimer);
            searchTimer = setTimeout(async () => {
                try {
                    const r = await fetch(`${API_BASE}/stocks/search?q=${encodeURIComponent(q)}`);
                    const d = await r.json();
                    stockSuggestions.value = d.rows || [];
                    stockSuggestionIdx.value = -1;
                } catch (e) {}
            }, 150);
        }

        function onStockKeydown(e) {
            const len = stockSuggestions.value.length;
            if (len === 0) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); stockSuggestionIdx.value = Math.min(stockSuggestionIdx.value + 1, len - 1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); stockSuggestionIdx.value = Math.max(stockSuggestionIdx.value - 1, 0); }
            else if (e.key === 'Enter' && stockSuggestionIdx.value >= 0) {
                e.preventDefault();
                selectStock(stockSuggestions.value[stockSuggestionIdx.value].stock_code);
            }
        }

        function selectStock(code) {
            stockCode.value = code;
            stockSuggestions.value = [];
            stockSuggestionIdx.value = -1;
            loadProfile();
        }

        async function checkWatchlist() {
            if (!stockCode.value) return;
            try {
                const r = await fetch(`${API_BASE}/watchlist/check?stock_code=${stockCode.value}`);
                const d = await r.json();
                inWatchlist.value = d.in_watchlist;
            } catch (e) {}
        }

        async function addToWatchlist() {
            try {
                await fetch(`${API_BASE}/watchlist/add?stock_code=${stockCode.value}`, { method: 'POST' });
                inWatchlist.value = true;
                watchlistCount.value++;
            } catch (e) {}
        }

        function removeFromWatchlist(code) {
            const sc = code || stockCode.value;
            (async () => {
                try {
                    await fetch(`${API_BASE}/watchlist/remove?stock_code=${sc}`, { method: 'POST' });
                    if (sc === stockCode.value) inWatchlist.value = false;
                    if (watchlistCount.value > 0) watchlistCount.value--;
                    if (activeTab.value === 'watchlist') loadWatchlist();
                } catch (e) {}
            })();
        }

        async function loadWatchlist() {
            watchlistLoading.value = true;
            try {
                const r = await fetch(`${API_BASE}/watchlist`);
                const d = await r.json();
                watchlistData.value = d;
                watchlistCount.value = d.total || 0;
                if (activeTab.value === 'watchlist') setNavList(d.rows);
            } catch (e) {} finally {
                watchlistLoading.value = false;
            }
        }

        const zxmFilterOptions = [
            { field: 'zxm_asset_weight', label: '资产结构', options: ['轻资产', '中资产', '重资产'] },
            { field: 'zxm_hematopoiesis', label: '资本结构', options: ['造血型', '均衡型', '输血型'] },
            { field: 'zxm_margin_level', label: '利润质量', options: ['高毛利', '中毛利', '低毛利'] },
            { field: 'zxm_cashflow_type', label: '现金流', options: ['现金奶牛', '现金正常', '纸面富贵', '失血状态'] },
            { field: 'zxm_growth_rate', label: '成长性', options: ['爆发增长', '高速增长', '稳健增长', '缓慢增长', '衰退'] },
            { field: 'zxm_growth_quality', label: '增长质量', options: ['增收增利', '增收平利', '增收不增利', '减收减利'] },
            { field: 'zxm_leverage', label: '杠杆', options: ['零杠杆', '低杠杆', '中杠杆', '高杠杆'] },
            { field: 'zxm_overall_rating', label: '综合评级', options: ['优秀', '良好', '中等', '中下', '差'] },
        ];
        const selectedZxmFilters = ref({});

        function toggleZxmFilter(field, val) {
            if (!selectedZxmFilters.value[field]) selectedZxmFilters.value[field] = {};
            if (selectedZxmFilters.value[field][val]) {
                delete selectedZxmFilters.value[field][val];
            } else {
                selectedZxmFilters.value[field][val] = true;
            }
            selectedZxmFilters.value = {...selectedZxmFilters.value};
            onFilterChange();
        }

        function isZxmFilterActive(field, val) {
            return selectedZxmFilters.value[field] && selectedZxmFilters.value[field][val];
        }

        function hasActiveZxmFilter() {
            for (const f in selectedZxmFilters.value) {
                for (const v in selectedZxmFilters.value[f]) {
                    if (selectedZxmFilters.value[f][v]) return true;
                }
            }
            return false;
        }

        function goToSimilar() {
            if (!zxmTags.value) return;
            const map = {
                asset_weight: 'zxm_asset_weight', hematopoiesis: 'zxm_hematopoiesis',
                margin_level: 'zxm_margin_level', cashflow_type: 'zxm_cashflow_type',
                growth_rate: 'zxm_growth_rate', growth_quality: 'zxm_growth_quality',
                leverage: 'zxm_leverage', overall_rating: 'zxm_overall_rating',
            };
            const preset = {};
            for (const [tagKey, filterField] of Object.entries(map)) {
                const val = zxmTags.value[tagKey];
                if (val && !['未知', '一般'].includes(val)) {
                    preset[filterField] = val;
                }
            }
            window._zxmSimilarPreset = preset;
            activeTab.value = 'screening';
        }

        const growthTagOptions = [
            { id: 'biz.annual_rev_growth_1y', label: '营收连增1年' },
            { id: 'biz.annual_rev_growth_2y', label: '营收连增2年' },
            { id: 'biz.annual_rev_growth_3y', label: '营收连增3年' },
            { id: 'biz.annual_rev_growth_4y', label: '营收连增4年' },
            { id: 'biz.annual_rev_growth_5y', label: '营收连增5年' },
            { id: 'biz.annual_rev_growth_6y', label: '营收连增6年' },
            { id: 'biz.annual_rev_growth_7y', label: '营收连增7年' },
            { id: 'biz.annual_rev_growth_8y', label: '营收连增8年' },
            { id: 'biz.annual_rev_growth_9y', label: '营收连增9年' },
            { id: 'biz.annual_profit_growth_1y', label: '利润连增1年' },
            { id: 'biz.annual_profit_growth_2y', label: '利润连增2年' },
            { id: 'biz.annual_profit_growth_3y', label: '利润连增3年' },
            { id: 'biz.annual_profit_growth_4y', label: '利润连增4年' },
            { id: 'biz.annual_profit_growth_5y', label: '利润连增5年' },
            { id: 'biz.annual_profit_growth_6y', label: '利润连增6年' },
            { id: 'biz.annual_profit_growth_7y', label: '利润连增7年' },
            { id: 'biz.annual_profit_growth_8y', label: '利润连增8年' },
            { id: 'biz.annual_profit_growth_9y', label: '利润连增9年' },
            { id: 'biz.annual_gm_improve_1y', label: '毛利率提升1年' },
            { id: 'biz.annual_gm_improve_2y', label: '毛利率连升2年' },
            { id: 'biz.annual_gm_improve_3y', label: '毛利率连升3年' },
            { id: 'biz.annual_gm_improve_4y', label: '毛利率连升4年' },
            { id: 'biz.tenbagger', label: '21年至今十倍股', style: 'highlight' },
        ];
        const selectedGrowthTags = ref([]);
        const sectorListIndustries = ref([]);
        const sectorListConcepts = ref([]);
        const selectedSectors = ref([]);

        async function loadSectors() {
            try {
                const ri = await fetch(`${API_BASE}/sectors?category=industry`);
                const di = await ri.json();
                sectorListIndustries.value = di.rows || [];
                const rc = await fetch(`${API_BASE}/sectors?category=concept`);
                const dc = await rc.json();
                sectorListConcepts.value = dc.rows || [];
            } catch (e) {}
        }

        function toggleSector(code) {
            const i = selectedSectors.value.indexOf(code);
            if (i >= 0) selectedSectors.value.splice(i, 1);
            else selectedSectors.value.push(code);
            onFilterChange();
        }

        const searchLoading = ref(false);
        const searchResult = ref(null);
        const sortBy = ref('tech_score');
        const sortOrder = ref('desc');
        const profileStatusData = ref(null);
        const refreshing = ref(false);
        const refreshProgress = ref('');
        const refreshToast = ref('');
        let refreshToastTimer = null;

        function toggleStage(id) {
            const i = selectedStages.value.indexOf(id);
            if (i >= 0) selectedStages.value.splice(i, 1);
            else selectedStages.value.push(id);
        }

        function toggleGrowthTag(id) {
            const i = selectedGrowthTags.value.indexOf(id);
            if (i >= 0) selectedGrowthTags.value.splice(i, 1);
            else selectedGrowthTags.value.push(id);
        }

        let searchDebounce = null;
        function onFilterChange() {
            if (searchDebounce) clearTimeout(searchDebounce);
            searchDebounce = setTimeout(doSearch, 400);
        }

        let searchSeq = 0;
        async function doSearch() {
            const seq = ++searchSeq;
            searchLoading.value = true;
            try {
                const zxmBody = {};
                for (const f of zxmFilterOptions) {
                    const sf = selectedZxmFilters.value[f.field];
                    if (sf) {
                        const keys = Object.keys(sf).filter(k => sf[k]);
                        if (keys.length === 1) zxmBody[f.field] = keys[0];
                    }
                }
                const body = {
                    stages: selectedStages.value,
                    sectors: selectedSectors.value,
                    tags: { must: selectedGrowthTags.value, must_not: [], any: [] },
                    tech_score_min: filterTechScore.value > 0 ? filterTechScore.value : null,
                    fund_score_min: filterFundScore.value > 0 ? filterFundScore.value : null,
                    revenue_growth_min: filterRevGrowth.value || null,
                    net_profit_growth_min: filterProfitGrowth.value || null,
                    prev_year_profit_min: filterPrevYearProfitMin.value != null ? filterPrevYearProfitMin.value * 1e8 : null,
                    prev_year_profit_max: filterPrevYearProfitMax.value != null ? filterPrevYearProfitMax.value * 1e8 : null,
                    cur_quarter_profit_min: filterCurQuarterProfitMin.value != null ? filterCurQuarterProfitMin.value * 1e8 : null,
                    cur_quarter_profit_max: filterCurQuarterProfitMax.value != null ? filterCurQuarterProfitMax.value * 1e8 : null,
                    debt_ratio_max: filterDebtMax.value || null,
                    gm_growth_q_min: filterGmGrowthQ.value || null,
                    gm_growth_2y_min: filterGmGrowth2y.value || null,
                    contract_liab_min: filterContractLiabMin.value || null,
                    contract_liab_max: filterContractLiabMax.value || null,
                    roe_min: filterRoeMin.value || null,
                    roe_max: filterRoeMax.value || null,
                    net_margin_min: filterNetMarginMin.value || null,
                    net_margin_max: filterNetMarginMax.value || null,
                    market_cap_min: filterMarketCapRange.value ? (marketCapRanges.find(r => r.label === filterMarketCapRange.value) || {}).min ?? null : null,
                    market_cap_max: filterMarketCapRange.value ? (marketCapRanges.find(r => r.label === filterMarketCapRange.value) || {}).max ?? null : null,
                roe_ttm_min: filterRoeTtmMin.value || null,
                roe_ttm_max: filterRoeTtmMax.value || null,
                pe_max: filterPeMax.value || null,
                peg_max: filterPegMax.value || null,
                dividend_yield_min: filterDividendYieldMin.value || null,
                dividend_yield_max: filterDividendYieldMax.value || null,
                has_dividend_this_year: filterHasDivThisYear.value || null,
                has_mid_year_dividend: filterHasMidYear.value || null,
                consecutive_dividend_years: filterConsecutiveDivYears.value || null,
                    rev_cagr_3y_min: filterRevCagr3yMin.value || null,
                    rev_cagr_3y_max: filterRevCagr3yMax.value || null,
                    rev_cagr_5y_min: filterRevCagr5yMin.value || null,
                    rev_cagr_5y_max: filterRevCagr5yMax.value || null,
                    profit_cagr_3y_min: filterProfitCagr3yMin.value || null,
                    profit_cagr_3y_max: filterProfitCagr3yMax.value || null,
                    profit_cagr_5y_min: filterProfitCagr5yMin.value || null,
                    profit_cagr_5y_max: filterProfitCagr5yMax.value || null,
                    ...zxmBody,
                    page: searchResult.value ? searchResult.value.page : 1,
                    page_size: 50,
                    sort_by: sortBy.value,
                    sort_order: sortOrder.value,
                };
                const r = await fetch(`${API_BASE}/profiles/search`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await r.json();
                if (seq !== searchSeq) return;
                if (!data.error) {
                    searchResult.value = data;
                    if (activeTab.value === 'screening') setNavList(data.rows);
                }
            } catch (e) {
                if (seq === searchSeq) console.error(e);
            } finally {
                if (seq === searchSeq) searchLoading.value = false;
            }
        }

        function toggleSort(field) {
            if (sortBy.value === field) {
                sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc';
            } else {
                sortBy.value = field;
                sortOrder.value = 'desc';
            }
            doSearch();
        }

        function sortArrow(field) {
            if (sortBy.value !== field) return '';
            return sortOrder.value === 'desc' ? ' ▼' : ' ▲';
        }

        function resetFilters() {
            selectedStages.value = [];
            filterTechScore.value = 0;
            filterFundScore.value = 0;
            filterRevGrowth.value = null;
            filterProfitGrowth.value = null;
            filterPrevYearProfitMin.value = null;
            filterPrevYearProfitMax.value = null;
            filterCurQuarterProfitMin.value = null;
            filterCurQuarterProfitMax.value = null;
            filterDebtMax.value = null;
            filterGmGrowthQ.value = null;
            filterGmGrowth2y.value = null;
            filterContractLiabMin.value = null;
            filterContractLiabMax.value = null;
            filterRoeMin.value = null;
            filterRoeMax.value = null;
            filterNetMarginMin.value = null;
            filterNetMarginMax.value = null;
            filterMarketCapRange.value = '';
            filterRoeTtmMin.value = null;
            filterRoeTtmMax.value = null;
            filterPeMax.value = null;
            filterPegMax.value = null;
            filterDividendYieldMin.value = null;
            filterDividendYieldMax.value = null;
            filterHasDivThisYear.value = false;
            filterHasMidYear.value = false;
            filterConsecutiveDivYears.value = null;
            filterRevCagr3yMin.value = null;
            filterRevCagr3yMax.value = null;
            filterRevCagr5yMin.value = null;
            filterRevCagr5yMax.value = null;
            filterProfitCagr3yMin.value = null;
            filterProfitCagr3yMax.value = null;
            filterProfitCagr5yMin.value = null;
            filterProfitCagr5yMax.value = null;
            selectedGrowthTags.value = [];
            selectedZxmFilters.value = {};
            selectedSectors.value = [];
            sortBy.value = 'tech_score';
            sortOrder.value = 'desc';
            searchResult.value = null;
        }

        async function loadStatus() {
            try {
                const r = await fetch(`${API_BASE}/profiles/status`);
                profileStatusData.value = await r.json();
            } catch (e) { /* ignore */ }
        }

        let refreshPoll = null;

        function startRefreshPoll() {
            if (refreshPoll) clearInterval(refreshPoll);
            refreshing.value = true;
            refreshPoll = setInterval(async () => {
                try {
                    const r = await fetch(`${API_BASE}/profiles/refresh/progress`);
                    const p = await r.json();
                    if (p.status === 'running') {
                        const pct = p.total > 0 ? Math.round(p.computed / p.total * 100) : 0;
                        refreshProgress.value = pct + '%';
                    } else {
                        clearInterval(refreshPoll);
                        refreshPoll = null;
                        refreshing.value = false;
                        refreshProgress.value = '';
                        refreshToast.value = '✓ 刷新完成！共计算 ' + p.total + ' 只股票';
                        if (refreshToastTimer) clearTimeout(refreshToastTimer);
                        refreshToastTimer = setTimeout(() => { refreshToast.value = ''; }, 4000);
                        await loadStatus();
                        if (searchResult.value) doSearch();
                    }
                } catch (e) {
                    clearInterval(refreshPoll);
                    refreshPoll = null;
                    refreshing.value = false;
                    refreshProgress.value = '';
                }
            }, 2000);
        }

        async function triggerRefresh() {
            if (refreshing.value) return;
            refreshing.value = true;
            refreshProgress.value = '启动中...';
            try {
                const r = await fetch(`${API_BASE}/profiles/refresh`, { method: 'POST' });
                if (!r.ok && r.status === 429) {
                    refreshProgress.value = '后台正在刷新...';
                }
                startRefreshPoll();
            } catch (e) {
                refreshing.value = false;
                refreshProgress.value = '';
            }
        }

        async function checkRunningRefresh() {
            try {
                const r = await fetch(`${API_BASE}/profiles/refresh/progress`);
                const p = await r.json();
                if (p.status === 'running') {
                    startRefreshPoll();
                }
            } catch (e) { /* ignore */ }
        }

        function applyZxmPreset() {
            const preset = window._zxmSimilarPreset;
            if (!preset) return;
            for (const [field, val] of Object.entries(preset)) {
                if (!selectedZxmFilters.value[field]) selectedZxmFilters.value[field] = {};
                selectedZxmFilters.value[field][val] = true;
            }
            selectedZxmFilters.value = {...selectedZxmFilters.value};
            window._zxmSimilarPreset = null;
            nextTick(() => doSearch());
        }

        watch(activeTab, (tab) => {
            if (tab === 'screening') applyZxmPreset();
            if (tab === 'watchlist') loadWatchlist();
        });

        onMounted(() => {
            if (window._profileStockCode) {
                stockCode.value = window._profileStockCode;
                window._profileStockCode = null;
            }
            if (window._screeningList) {
                navList.value = window._screeningList;
                window._screeningList = null;
            }
            loadProfile();
            loadStatus();
            checkRunningRefresh();
            loadSectors();
            document.addEventListener('keydown', onKeydown);
        });
        onUnmounted(() => {
            document.removeEventListener('keydown', onKeydown);
        });

        return {
            activeTab, stockCode, loading, profile, error, finChartLoading, finChartCanvas, fundChartLoading, fundChartImg, fundChartImgEl, divChartCanvas,
            loadProfile, loadFinChart, loadFundChart, loadDivChart, scoreClass, scoreTextClass, rsiClass, debtClass, gmTrendClass, goToProfile, introStatusName, chainName,
            stageOptions, selectedStages, filterTechScore, filterFundScore,
            filterRevGrowth, filterProfitGrowth, filterDebtMax,
            filterPrevYearProfitMin, filterPrevYearProfitMax, filterCurQuarterProfitMin, filterCurQuarterProfitMax,
            filterGmGrowthQ, filterGmGrowth2y,
            filterContractLiabMin, filterContractLiabMax,
            filterRoeMin, filterRoeMax, filterRoeTtmMin, filterRoeTtmMax,
            filterNetMarginMin, filterNetMarginMax, filterMarketCapRange, marketCapRanges,
            filterDividendYieldMin, filterDividendYieldMax,
            filterHasDivThisYear, filterHasMidYear, filterConsecutiveDivYears,
            filterRevCagr3yMin, filterRevCagr3yMax, filterRevCagr5yMin, filterRevCagr5yMax,
            filterProfitCagr3yMin, filterProfitCagr3yMax, filterProfitCagr5yMin, filterProfitCagr5yMax,
            growthTagOptions, selectedGrowthTags,
            zxmFilterOptions, selectedZxmFilters, toggleZxmFilter, isZxmFilterActive, hasActiveZxmFilter,
            searchLoading, searchResult, profileStatusData, sortBy, sortOrder,
            refreshing, refreshProgress, refreshToast,
            sectorListIndustries, sectorListConcepts, selectedSectors, toggleSector,
            toggleStage, toggleGrowthTag, onFilterChange, doSearch, resetFilters, triggerRefresh,
            toggleSort, sortArrow,
            fmt, fmtGrowth, fmtMoney, valClass,
            zxmTags, zxmLoading, zxmClass, goToSimilar,
            currentIdx, hasPrev, hasNext, goPrev, goNext, navTotal, navList,
            stockSuggestions, stockSuggestionIdx, onStockInput, onStockKeydown, selectStock,
            inWatchlist, watchlistLoading, watchlistData, watchlistCount,
            addToWatchlist, removeFromWatchlist, loadWatchlist,
        };
    },
});

app.component('dividend-page', {
    template: '#dividend-tpl',
    setup() {
        const currentPage = inject('currentPage');
        const years = ref([]);
        for (let y = new Date().getFullYear(); y >= 2018; y--) years.value.push(y);
        const year = ref(new Date().getFullYear());
        const isMid = ref(0);
        const sort = ref('ex_dividend_date');
        const order = ref('desc');
        const page = ref(1);
        const pageSize = ref(50);
        const total = ref(0);
        const rows = ref([]);
        const loading = ref(false);
        const error = ref('');

        async function loadList() {
            loading.value = true;
            error.value = '';
            try {
                const params = new URLSearchParams({
                    year: year.value || '', is_mid: isMid.value, sort: sort.value, order: order.value,
                    page: page.value, page_size: pageSize.value,
                });
                const r = await fetch(`${API_BASE}/dividends/list?${params}`);
                const d = await r.json();
                if (d.error) error.value = d.error;
                else { rows.value = d.rows; total.value = d.total; }
            } catch (e) { error.value = e.message; } finally { loading.value = false; }
        }

        function toggleSort(col) {
            if (sort.value === col) { order.value = order.value === 'desc' ? 'asc' : 'desc'; }
            else { sort.value = col; order.value = 'desc'; }
            page.value = 1;
            loadList();
        }

        function sortArrow(col) {
            if (sort.value !== col) return '';
            return order.value === 'desc' ? '↓' : '↑';
        }

        function goStock(code) {
            window._profileStockCode = code;
            currentPage.value = 'profile';
        }

        function onFilter() { page.value = 1; loadList(); }

        function yieldTip(row) {
            if (row.dividend_yield == null) return '';
            return `股息率 = 每股派息 ${row.bonus_per_share ?? '-'}元 ÷ 除息日股价 × 100% = ${row.dividend_yield.toFixed(2)}%\n即一年现金分红相对股价的回报率`;
        }

        function payoutTip(row) {
            if (row.payout_ratio == null) return '';
            return `派息率（分红比例）= 每股派息 ${row.bonus_per_share ?? '-'}元 ÷ 每股收益 ${row.eps ?? '-'}元 × 100% = ${row.payout_ratio.toFixed(1)}%\n即当年利润中拿来分红的比例`;
        }

        const planWidth = ref(260);
        function startResize(ev) {
            const startX = ev.clientX;
            const startW = planWidth.value;
            const onMove = (e) => {
                planWidth.value = Math.max(120, startW + (e.clientX - startX));
            };
            const onUp = () => {
                window.removeEventListener('mousemove', onMove);
                window.removeEventListener('mouseup', onUp);
            };
            window.addEventListener('mousemove', onMove);
            window.addEventListener('mouseup', onUp);
        }

        onMounted(loadList);
        return { years, year, isMid, sort, order, page, pageSize, total, rows, loading, error, loadList, toggleSort, sortArrow, goStock, onFilter, yieldTip, payoutTip, planWidth, startResize };
    },
});

// ── Markdown Renderer ──
function renderMarkdown(text) {
    if (!text) return '';
    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
    html = html.replace(/^-{3,}$/gm, '<hr>');
    html = html.replace(/\n/g, '<br>');
    html = html.replace(/\|(.+)\|/g, (match) => {
        if (match.includes('---')) return '';
        const cells = match.split('|').filter(c => c.trim());
        const cols = cells.map(c => `<td>${c.trim()}</td>`).join('');
        return `<tr>${cols}</tr>`;
    });
    return html;
}

// ── AI Debate ──
app.component('debate-page', {
    template: '#debate-tpl',
    setup() {
        const stockCode = ref('600519');
        const loading = ref(false);
        const error = ref('');
        const result = ref(null);

        async function startDebate() {
            if (!stockCode.value) return;
            loading.value = true;
            error.value = '';
            result.value = null;
            try {
                const r = await fetch(`${API_BASE}/debate/start?stock_code=${encodeURIComponent(stockCode.value)}`, { method: 'POST' });
                const data = await r.json();
                if (data.error) error.value = data.error;
                else result.value = data;
            } catch (e) {
                error.value = '请求失败: ' + e.message;
            } finally {
                loading.value = false;
            }
        }

        return {
            stockCode, loading, error, result,
            startDebate,
            renderMarkdown, fmt, fmtGrowth, fmtMoney, valClass,
        };
    },
});

app.component('vcp-page', {
    template: '#vcp-tpl',
    setup() {
        const loading = ref(false);
        const result = ref(null);
        const scanTime = ref(0);
        const scannedCount = ref(0);
        const minContractions = ref(2);
        const maxContractions = ref(6);
        const minPct = ref(3);
        const lookbackDays = ref(150);

        function renderVcpCharts() {
            nextTick(() => {
                setTimeout(() => {
                    document.querySelectorAll('.vcp-chart-wrap').forEach(el => {
                        if (el._chart) return;
                        if (!result.value) return;
                        const si = parseInt(el.getAttribute('data-idx') || '-1');
                        if (si < 0 || si >= result.value.rows.length) return;
                        const stock = result.value.rows[si];
                        const cd = stock.chart_data;
                        if (!cd || cd.length < 3) return;

                        const parent = el.parentElement;
                        const w = Math.min((parent ? parent.clientWidth : 380) - 16, 400);

                        el._chart = LightweightCharts.createChart(el, {
                            width: w, height: 150,
                            layout: { background: { color: 'transparent' }, textColor: '#8e8ea0', fontSize: 9 },
                            grid: { vertLines: { color: '#1e1e35' }, horzLines: { color: '#1e1e35', style: 2 } },
                            timeScale: { borderColor: '#2a2a40', visible: false },
                            rightPriceScale: { borderColor: '#2a2a40', visible: true, scaleMargins: { top: 0.1, bottom: 0.3 } },
                            crosshair: { mode: 0 },
                            handleScroll: false, handleScale: false,
                        });

                        const cs = el._chart.addCandlestickSeries({
                            upColor: '#ef4444', downColor: '#10b981',
                            borderUpColor: '#ef4444', borderDownColor: '#10b981',
                            wickUpColor: '#ef4444', wickDownColor: '#10b981',
                            priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
                        });
                        cs.setData(cd.map(d => ({
                            time: d.date.replace(/-/g, ''),
                            open: d.open, high: d.high, low: d.low, close: d.close,
                        })));

                        if (stock.vcp_markers && stock.vcp_markers.length) {
                            cs.setMarkers(stock.vcp_markers.map(m => ({
                                time: m.time.replace(/-/g, ''),
                                position: m.position,
                                color: m.color,
                                shape: m.shape,
                                text: m.text,
                            })));
                        }

                        const lastN = Math.min(cd.length - 1, 60);
                        if (lastN > 10) {
                            el._chart.timeScale().setVisibleLogicalRange({
                                from: cd.length - 1 - lastN,
                                to: cd.length - 1,
                            });
                        }
                    });
                }, 200);
            });
        }

        async function scan() {
            loading.value = true;
            result.value = null;
            scanTime.value = 0;
            const start = Date.now();
            try {
                const params = new URLSearchParams({
                    min_contractions: minContractions.value,
                    max_contractions: maxContractions.value,
                    min_pct: minPct.value,
                    lookback_days: lookbackDays.value,
                    max_stocks: 50,
                });
                const r = await fetch(`${API_BASE}/vcp/scan?${params}`);
                const data = await r.json();
                result.value = data;
                scannedCount.value = data.total || 0;
            } catch (e) {
                console.error(e);
            } finally {
                loading.value = false;
                scanTime.value = ((Date.now() - start) / 1000).toFixed(1);
                renderVcpCharts();
            }
        }

        return {
            loading, result, scanTime, scannedCount,
            minContractions, maxContractions, minPct, lookbackDays,
            scan, fmt,
        };
    },
});

app.component('expert-page', {
    template: '#expert-tpl',
    setup() {
        const experts = ref([]);
        const availableExperts = ref([]);
        const selectedExpert = ref('');
        const expertName = ref('');
        const expertDesc = ref('');
        const stockCode = ref('');
        const question = ref('');
        const loading = ref(false);
        const error = ref('');
        const messages = ref([]);
        const stockData = ref(null);
        const finData = ref(null);
        const chatBottom = ref(null);

        async function loadExperts() {
            try {
                const r = await fetch(`${API_BASE}/expert/list`);
                const data = await r.json();
                experts.value = data.experts || [];
                availableExperts.value = data.experts || [];
            } catch (e) {
                error.value = '加载专家列表失败: ' + e.message;
            }
        }

        function switchExpert() {
            messages.value = [];
            stockData.value = null;
            finData.value = null;
            error.value = '';
            const e = experts.value.find(x => x.id === selectedExpert.value);
            expertName.value = e ? e.name : '';
            expertDesc.value = e ? e.description : '';
        }

        async function send() {
            if (!selectedExpert.value || !stockCode.value || !question.value) return;
            if (loading.value) return;

            error.value = '';
            const q = question.value;
            question.value = '';

            messages.value.push({ role: 'user', content: q });

            const typingMsg = { role: 'expert', content: '', typing: true };
            messages.value.push(typingMsg);
            scrollBottom();
            loading.value = true;

            const history = [];
            for (let i = 0; i < messages.value.length - 2; i += 2) {
                const u = messages.value[i];
                const a = messages.value[i + 1];
                if (u.role === 'user' && a.role === 'expert') {
                    history.push({ question: u.content, answer: a.content });
                }
            }

            try {
                const r = await fetch(`${API_BASE}/expert/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        expert_id: selectedExpert.value,
                        stock_code: stockCode.value,
                        question: q,
                        history: history,
                    }),
                });
                const data = await r.json();

                if (data.error) {
                    messages.value.pop();
                    messages.value.push({ role: 'expert', content: '⚠️ ' + data.error });
                } else {
                    typingMsg.typing = false;
                    typingMsg.content = data.answer;
                    stockData.value = data.stock;
                    finData.value = data.financials;
                }
            } catch (e) {
                messages.value.pop();
                messages.value.push({ role: 'expert', content: '⚠️ 请求失败: ' + e.message });
            } finally {
                loading.value = false;
                scrollBottom();
            }
        }

        function scrollBottom() {
            setTimeout(() => {
                if (chatBottom.value) {
                    chatBottom.value.scrollIntoView({ behavior: 'smooth' });
                }
            }, 50);
        }

        function finClass(val) {
            if (val == null) return '';
            if (val > 0) return 'up';
            if (val < 0) return 'down';
            return '';
        }

        onMounted(loadExperts);

        return {
            experts, availableExperts, selectedExpert, expertName, expertDesc,
            stockCode, question, loading, error, messages, stockData, finData, chatBottom,
            switchExpert, send, scrollBottom, finClass,
            renderMarkdown, fmt, fmtGrowth, valClass,
        };
    },
});

// ── Data Management ──
app.component('data-mgmt-page', {
    template: '#data-mgmt-tpl',
    setup() {
        const status = ref({ kline: {}, financial: {}, sector: {} });
        const klineLoading = ref(false);
        const klineResult = ref('');
        const klineError = ref('');
        const qfqLoading = ref(false);
        const qfqResult = ref('');
        const qfqError = ref('');
        const qfqProgress = ref('');
        const finLoading = ref(false);
        const finResult = ref('');
        const finError = ref('');

        const lastSyncLabel = computed(() => {
            const d = status.value.kline?.latest_date;
            if (!d) return '暂无数据';
            const today = new Date();
            const kDate = new Date(d);
            const diff = Math.floor((today - kDate) / (1000 * 60 * 60 * 24));
            if (diff === 0) return '今天';
            if (diff === 1) return '昨天';
            if (diff < 7) return diff + '天前';
            return d;
        });

        const finDotClass = computed(() => {
            const d = status.value.financial?.latest_date;
            return d ? 'dm-dot-online' : 'dm-dot-pending';
        });

        const finStatusText = computed(() => {
            const d = status.value.financial?.latest_date;
            return d ? '已同步' : '待接入';
        });

        async function loadStatus() {
            try {
                const r = await fetch(`${API_BASE}/data/status`);
                status.value = await r.json();
            } catch (e) { console.error(e); }
        }

        async function updateKline() {
            klineLoading.value = true;
            klineResult.value = '';
            klineError.value = '';
            try {
                const r = await fetch(`${API_BASE}/data/update-kline`, { method: 'POST' });
                const data = await r.json();
                if (data.status === 'running') {
                    klineResult.value = '更新任务已在执行中';
                } else {
                    const n = data.total_inserted ?? 0;
                    if (n > 0) {
                        klineResult.value = `成功插入 ${n} 条新记录`;
                    } else {
                        const latest = data.db_latest || '?';
                        klineResult.value = `数据已是最新（截至 ${latest}）`;
                    }
                    loadStatus();
                }
            } catch (e) {
                klineError.value = e.message;
            } finally {
                klineLoading.value = false;
            }
        }

        async function updateFinancial() {
            finLoading.value = true;
            finResult.value = '';
            finError.value = '';
            try {
                const r = await fetch(`${API_BASE}/data/update-financial`, { method: 'POST' });
                const data = await r.json();
                if (data.status === 'running') {
                    finResult.value = '同步任务已在执行中';
                } else if (data.message) {
                    finResult.value = data.message;
                } else {
                    const n = data.total_inserted ?? 0;
                    if (n > 0) {
                        const files = (data.files || []).map(f => f.file.replace('gpcw', '').replace('.dat', '')).join(', ');
                        finResult.value = `成功同步 ${n} 条记录（${files}）`;
                    } else {
                        finResult.value = '财务数据已是最新';
                    }
                    loadStatus();
                }
            } catch (e) {
                finError.value = e.message;
            } finally {
                finLoading.value = false;
            }
        }

        const qfqDotClass = computed(() => {
            return qfqLoading.value ? 'dm-dot-sync' : (status.value.qfq?.row_count ? 'dm-dot-online' : 'dm-dot-pending');
        });
        const qfqStatusText = computed(() => {
            return qfqLoading.value ? '重算中' : (status.value.qfq?.row_count ? '已生成' : '待计算');
        });

        function fmtQfqRows(n) {
            if (!n) return '0 条';
            if (n >= 1e8) return (n / 1e8).toFixed(2) + ' 亿条';
            if (n >= 1e4) return (n / 1e4).toFixed(1) + ' 万条';
            return n + ' 条';
        }

        let qfqPollInterval = null;
        async function updateQfq() {
            if (qfqLoading.value) return;
            qfqLoading.value = true;
            qfqResult.value = '';
            qfqError.value = '';
            qfqProgress.value = '';
            try {
                const r = await fetch(`${API_BASE}/data/update-qfq`, { method: 'POST' });
                const data = await r.json();
                if (data.status === 'running') {
                    qfqResult.value = '前复权计算已在执行中';
                    qfqLoading.value = false;
                    return;
                }
                if (data.status === 'error') {
                    qfqError.value = data.message || '计算失败';
                    qfqLoading.value = false;
                    return;
                }
                qfqResult.value = data.message || '已启动';
                qfqPollInterval = setInterval(async () => {
                    try {
                        const p = await fetch(`${API_BASE}/data/qfq/status`);
                        const d = await p.json();
                        if (d.status === 'running') {
                            const lastLine = (d.log_tail || '').split('\n').filter(Boolean).pop() || '';
                            const m = lastLine.match(/进度: (\d+)\/(\d+)/);
                            qfqProgress.value = m ? Math.round(m[1] / m[2] * 100) + '%' : '运行中';
                        } else {
                            clearInterval(qfqPollInterval);
                            qfqPollInterval = null;
                            qfqLoading.value = false;
                            qfqProgress.value = '';
                            const done = (d.log_tail || '').split('\n').filter(Boolean).pop() || '';
                            qfqResult.value = done.includes('完成') ? done : '前复权K线已更新';
                            loadStatus();
                        }
                    } catch (e) {
                        clearInterval(qfqPollInterval);
                        qfqPollInterval = null;
                        qfqLoading.value = false;
                        qfqProgress.value = '';
                        qfqError.value = '轮询失败: ' + e.message;
                    }
                }, 5000);
            } catch (e) {
                qfqError.value = e.message;
                qfqLoading.value = false;
            }
        }

        const divLoading = ref(false);
        const divResult = ref('');
        const divError = ref('');

        const divDotClass = computed(() => {
            return divLoading.value ? 'dm-dot-sync' : (status.value.dividend?.latest_update ? 'dm-dot-online' : 'dm-dot-pending');
        });

        const divStatusText = computed(() => {
            return divLoading.value ? '更新中' : (status.value.dividend?.latest_update ? '已同步' : '待接入');
        });

        const sectorLoading = ref(false);
        const sectorResult = ref('');
        const sectorError = ref('');

        const sectorDotClass = computed(() => {
            return sectorLoading.value ? 'dm-dot-sync' : (status.value.sector?.sector_count ? 'dm-dot-online' : 'dm-dot-pending');
        });

        const sectorStatusText = computed(() => {
            return sectorLoading.value ? '同步中' : (status.value.sector?.sector_count ? '已同步' : '待接入');
        });

        async function updateSector() {
            sectorLoading.value = true;
            sectorResult.value = '';
            sectorError.value = '';
            try {
                const r = await fetch(`${API_BASE}/data/update-sector`, { method: 'POST' });
                const data = await r.json();
                if (data.status === 'running') {
                    sectorResult.value = '同步任务已在执行中';
                } else if (data.status === 'error') {
                    sectorError.value = data.message || '同步失败';
                } else {
                    sectorResult.value = `同步完成：${data.sector_count} 个板块 / ${data.mapping_count} 条映射`;
                    loadStatus();
                }
            } catch (e) {
                sectorError.value = e.message;
            } finally {
                sectorLoading.value = false;
            }
        }

        async function updateDividend() {
            divLoading.value = true;
            divResult.value = '';
            divError.value = '';
            try {
                const r = await fetch(`${API_BASE}/data/update-dividend`, { method: 'POST' });
                const data = await r.json();
                if (data.status === 'running') {
                    divResult.value = '更新任务已在执行中';
                } else if (data.status === 'error') {
                    divError.value = data.message || '更新失败';
                } else {
                    divResult.value = `增量更新完成（自 ${data.since}）`;
                    loadStatus();
                }
            } catch (e) {
                divError.value = e.message;
            } finally {
                divLoading.value = false;
            }
        }

        const profileRefreshing = ref(false);
        const refreshProgressBar = ref('');
        const profileRefreshDone = ref('');
        const profileRefreshData = ref(null);
        let profileRefreshPollInterval = null;

        const profileRefreshDot = computed(() => {
            return profileRefreshing.value ? 'dm-dot-sync' : (profileRefreshData.value?.last_refresh_time ? 'dm-dot-online' : 'dm-dot-pending');
        });
        const profileRefreshStatusText = computed(() => {
            return profileRefreshing.value ? '刷新中' : (profileRefreshData.value?.last_refresh_time ? '已缓存' : '未缓存');
        });

        async function loadProfileRefreshStatus() {
            try {
                const r = await fetch(`${API_BASE}/profiles/status`);
                profileRefreshData.value = await r.json();
            } catch (e) {}
        }

        async function triggerDataRefresh() {
            if (profileRefreshing.value) return;
            profileRefreshing.value = true;
            profileRefreshDone.value = '';
            refreshProgressBar.value = '启动中';
            const startTime = Date.now();
            try {
                const r = await fetch(`${API_BASE}/profiles/refresh`, { method: 'POST' });
                if (!r.ok && r.status === 429) {
                    refreshProgressBar.value = '后台正在刷新';
                }
                profileRefreshPollInterval = setInterval(async () => {
                    try {
                        const p = await fetch(`${API_BASE}/profiles/refresh/progress`);
                        const d = await p.json();
                        if (d.status === 'running') {
                            const pct = d.total > 0 ? Math.round(d.computed / d.total * 100) : 0;
                            refreshProgressBar.value = pct + '%';
                        } else {
                            clearInterval(profileRefreshPollInterval);
                            profileRefreshPollInterval = null;
                            profileRefreshing.value = false;
                            refreshProgressBar.value = '';
                            const elapsed = Math.round((Date.now() - startTime) / 1000);
                            profileRefreshDone.value = `完成！${d.computed || 0} 只股票，耗时 ${elapsed}s`;
                            loadProfileRefreshStatus();
                        }
                    } catch (e) {
                        clearInterval(profileRefreshPollInterval);
                        profileRefreshPollInterval = null;
                        profileRefreshing.value = false;
                        refreshProgressBar.value = '';
                    }
                }, 2000);
            } catch (e) {
                profileRefreshing.value = false;
                refreshProgressBar.value = '';
            }
        }

        onMounted(() => {
            loadStatus();
            loadProfileRefreshStatus();
            loadDmdlStatus();
        });

        const adsLoading = ref(false);
        const adsResult = ref('');
        const adsError = ref('');

        const adsDotClass = computed(() => {
            return adsLoading.value ? 'dm-dot-sync' : (status.value.ads?.last_run ? 'dm-dot-online' : 'dm-dot-pending');
        });
        const adsStatusText = computed(() => {
            return adsLoading.value ? '计算中' : (status.value.ads?.status === 'running' ? '运行中' : (status.value.ads?.last_run ? '已计算' : '待计算'));
        });

        async function updateAds() {
            adsLoading.value = true;
            adsResult.value = '';
            adsError.value = '';
            try {
                const r = await fetch(`${API_BASE}/data/update-ads`, { method: 'POST' });
                const data = await r.json();
                if (data.status === 'running') {
                    adsResult.value = '预计算任务已在执行中';
                } else if (data.status === 'error') {
                    adsError.value = data.message || '计算失败';
                } else {
                    adsResult.value = data.message || '预计算已启动';
                }
                setTimeout(loadStatus, 1500);
            } catch (e) {
                adsError.value = e.message;
            } finally {
                adsLoading.value = false;
            }
        }

        const dmdlLoading = ref(false);
        const dmdlResult = ref('');
        const dmdlStatus = ref(null);

        const dmdlDotClass = computed(() => {
            return dmdlLoading.value ? 'dm-dot-sync' : (dmdlStatus.value?.static?.count ? 'dm-dot-online' : 'dm-dot-pending');
        });
        const dmdlStatusText = computed(() => {
            return dmdlLoading.value ? '计算中' : (dmdlStatus.value?.static?.count ? '已计算' : '待计算');
        });

        async function loadDmdlStatus() {
            try {
                const r = await fetch(`${API_BASE}/dmdl/status`);
                dmdlStatus.value = await r.json();
            } catch (e) {}
        }

        async function updateDmdl() {
            dmdlLoading.value = true;
            dmdlResult.value = '';
            try {
                const r = await fetch(`${API_BASE}/dmdl/update`, { method: 'POST' });
                const data = await r.json();
                dmdlResult.value = data.message || '已启动';
                setTimeout(loadDmdlStatus, 3000);
            } catch (e) {
                dmdlResult.value = '失败: ' + e.message;
            } finally {
                dmdlLoading.value = false;
            }
        }

        return {
            status, klineLoading, klineResult, klineError,
            qfqLoading, qfqResult, qfqError, qfqProgress, qfqDotClass, qfqStatusText, fmtQfqRows, updateQfq,
            finLoading, finResult, finError,
            divLoading, divResult, divError, divDotClass, divStatusText, updateDividend,
            sectorLoading, sectorResult, sectorError, sectorDotClass, sectorStatusText, updateSector,
            lastSyncLabel, finDotClass, finStatusText,
            updateKline, updateFinancial,
            profileRefreshDot, profileRefreshStatusText,
            profileRefreshing, refreshProgressBar, profileRefreshDone, profileRefreshData,
            triggerDataRefresh, loadProfileRefreshStatus,
            adsLoading, adsResult, adsError, adsDotClass, adsStatusText, updateAds,
            dmdlLoading, dmdlResult, dmdlStatus, dmdlDotClass, dmdlStatusText, updateDmdl,
        };
    },
});

// ── 达摩达兰估值 ──
app.component('dmdl-page', {
    template: '#dmdl-tpl',
    setup() {
        const rows = ref([]);
        const loading = ref(false);
        const selected = ref(null);
        const status = ref({ mkt: {}, sector: {}, valuation_view: {} });
        const filters = reactive({ stage: '', min_score: 0, stock_code: '' });
        const stockQuery = ref('');
        const stockSuggestions = ref([]);
        const stockSuggestionIdx = ref(-1);
        let searchTimer = null;

        function stageLabel(s) {
            const map = { growth: '成长', cycle: '周期', finance: '金融', turnaround: '困境反转', decline: '衰退' };
            return map[s] || s || '-';
        }

        async function onStockInput() {
            const q = stockQuery.value.trim();
            if (q.length < 1) { stockSuggestions.value = []; return; }
            if (searchTimer) clearTimeout(searchTimer);
            searchTimer = setTimeout(async () => {
                try {
                    const r = await fetch(`${API_BASE}/stocks/search?q=${encodeURIComponent(q)}`);
                    const d = await r.json();
                    stockSuggestions.value = d.rows || [];
                    stockSuggestionIdx.value = -1;
                } catch (e) {}
            }, 150);
        }

        function onStockKeydown(e) {
            const len = stockSuggestions.value.length;
            if (len === 0) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); stockSuggestionIdx.value = Math.min(stockSuggestionIdx.value + 1, len - 1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); stockSuggestionIdx.value = Math.max(stockSuggestionIdx.value - 1, 0); }
            else if (e.key === 'Enter' && stockSuggestionIdx.value >= 0) {
                e.preventDefault();
                selectStock(stockSuggestions.value[stockSuggestionIdx.value].stock_code);
            }
        }

        function selectFirstSuggestion() {
            if (stockSuggestions.value.length) {
                selectStock(stockSuggestions.value[0].stock_code);
            } else if (stockQuery.value.trim()) {
                selectStock(stockQuery.value.trim());
            }
        }

        async function selectStock(code) {
            stockQuery.value = code;
            stockSuggestions.value = [];
            stockSuggestionIdx.value = -1;
            filters.stock_code = code;
            await Promise.all([loadValuation(), openStock(code)]);
        }

        async function loadValuation() {
            loading.value = true;
            try {
                const params = new URLSearchParams();
                if (filters.stock_code) {
                    params.set('stock_code', filters.stock_code);
                } else {
                    if (filters.stage) params.set('stage', filters.stage);
                    if (filters.min_score) params.set('min_score', filters.min_score);
                }
                params.set('limit', 100);
                const r = await fetch(`${API_BASE}/dmdl/valuation?${params}`);
                rows.value = await r.json();
                const s = await (await fetch(`${API_BASE}/dmdl/status`)).json();
                status.value = s;
            } catch (e) { console.error(e); }
            finally { loading.value = false; }
        }

        async function openStock(code) {
            try {
                const r = await fetch(`${API_BASE}/dmdl/stock/${code}`);
                selected.value = await r.json();
                if (selected.value.stock_name && stockQuery.value !== selected.value.stock_code) {
                    stockQuery.value = `${selected.value.stock_code} ${selected.value.stock_name}`;
                }
            } catch (e) { console.error(e); }
        }

        function resetFilter() {
            filters.stock_code = '';
            stockQuery.value = '';
            selected.value = null;
            loadValuation();
        }

        watch([() => filters.stage, () => filters.min_score], () => {
            if (filters.stock_code) {
                filters.stock_code = '';
                stockQuery.value = '';
            }
            loadValuation();
        });
        watch(() => filters.stock_code, loadValuation);
        onMounted(loadValuation);

        return { rows, loading, selected, status, filters, stageLabel, loadValuation, openStock, resetFilter,
                 stockQuery, stockSuggestions, stockSuggestionIdx,
                 onStockInput, onStockKeydown, selectFirstSuggestion, selectStock, fmt, fmtGrowth, fmtMoney };
    },
});

app.component('query-page', {
    template: '#query-tpl',
    setup() {
        const messages = ref([]);
        const inputText = ref('');
        const loading = ref(false);
        const msgBox = ref(null);

        function renderMarkdown(text) {
            if (!text) return '';
            let html = text
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
                    const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    return `<pre class="code-block"><code>${escaped}</code></pre>`;
                })
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                .replace(/\*([^*]+)\*/g, '<em>$1</em>')
                .replace(/\n/g, '<br>');
            return html;
        }

        function cellClass(val) {
            if (val == null) return '';
            const n = Number(val);
            if (isNaN(n)) return '';
            if (n > 0) return 'up';
            if (n < 0) return 'down';
            return '';
        }

        function scrollBottom() {
            nextTick(() => {
                const el = msgBox.value;
                if (el) el.scrollTop = el.scrollHeight;
            });
        }

        async function ask(text) {
            if (!text || !text.trim() || loading.value) return;
            const q = text.trim();
            inputText.value = '';
            messages.value.push({ role: 'user', content: q, sections: [] });
            loading.value = true;
            scrollBottom();

            try {
                const hist = messages.value.filter(m => m.role === 'user' || m.role === 'assistant')
                    .map(m => ({
                        question: m.role === 'user' ? m.content : '',
                        answer: m.role === 'assistant' ? m.content : '',
                    }));
                const resp = await fetch('/api/query/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: q, history: hist }),
                });
                const data = await resp.json();
                messages.value.push({ role: 'assistant', content: data.answer || '暂无回复', sections: data.sections || [] });
            } catch (e) {
                messages.value.push({ role: 'assistant', content: '请求失败: ' + e.message, sections: [] });
            } finally {
                loading.value = false;
                scrollBottom();
            }
        }

        watch(messages, () => {
            nextTick(() => {
                document.querySelectorAll('.kline-chart').forEach(el => {
                    if (el._chart) return;
                    const chartId = el.getAttribute('data-chart');
                    if (!chartId) return;
                    try {
                        const parts = chartId.split('_');
                        const msgIdx = parseInt(parts[1]);
                        const secIdx = parseInt(parts[2]);
                        const msg = messages.value[msgIdx];
                        if (!msg || !msg.sections[secIdx] || msg.sections[secIdx].type !== 'chart') return;
                        const chartData = msg.sections[secIdx].data;
                        if (!chartData || chartData.length < 3) return;

                        el._chart = LightweightCharts.createChart(el, {
                            width: el.parentElement.clientWidth - 20,
                            height: 340,
                            layout: { background: { color: '#131322' }, textColor: '#8e8ea0' },
                            grid: { vertLines: { color: '#1e1e35' }, horzLines: { color: '#1e1e35' } },
                            timeScale: { borderColor: '#2a2a40', timeVisible: true },
                            rightPriceScale: { borderColor: '#2a2a40' },
                        });
                        el._candleSeries = el._chart.addCandlestickSeries({
                            upColor: '#26a69a', downColor: '#ef5350',
                            borderUpColor: '#26a69a', borderDownColor: '#ef5350',
                            wickUpColor: '#26a69a', wickDownColor: '#ef5350',
                        });
                        el._candleSeries.setData(chartData.map(d => ({
                            time: d.date.replace(/-/g, ''),
                            open: d.open,
                            high: d.high,
                            low: d.low,
                            close: d.close,
                        })));
                        const volSeries = el._chart.addHistogramSeries({
                            color: '#3a6ea5', priceFormat: { type: 'volume' },
                            priceScaleId: 'volume',
                        });
                        el._chart.priceScale('volume').applyOptions({
                            scaleMargins: { top: 0.8, bottom: 0 },
                        });
                        volSeries.setData(chartData.map(d => ({
                            time: d.date.replace(/-/g, ''),
                            value: d.volume,
                            color: d.close >= d.open ? '#26a69a66' : '#ef535066',
                        })));
                        el._chart.timeScale().fitContent();
                    } catch (e) { console.error('Chart render error:', e); }
                });
            });
        }, { deep: true });

        return { messages, inputText, loading, msgBox, renderMarkdown, cellClass, ask };
    },
});

window.CHART_COLORS = ['#26a69a', '#ef5350', '#42a5f5', '#ffa726', '#ab47bc', '#5c6bc0'];

app.component('strong-page', {
    template: '#strong-tpl',
    setup() {
        const indexData = ref(null);
        const sectors = ref([]);
        const loading = ref(false);
        const error = ref('');
        const category = ref('industry');
        const industryLevel = ref('all');
        const prosperityFilter = ref('all');
        const showFinCols = computed(() => category.value === 'industry' || category.value === 'concept');
        const sortBy = ref('relative_ytd');
        const sortOrder = ref('desc');
        const dates = ref({});

        const chartCodes = ref(['000001']);
        const chartDays = ref(120);
        const chartSeries = ref([]);
        const chartLoading = ref(false);

        const financeData = ref(null);
        const financeIndex = ref(0);
        const finQuarter = ref('annual');
        const finSearch = ref('');
        const filteredSectors = computed(() => {
            const q = finSearch.value.trim().toLowerCase();
            if (!q) return [];
            return sectors.value.filter(s => s.sector_name.toLowerCase().includes(q) || s.sector_code.includes(q)).slice(0, 30);
        });
        function selectFinSector(code) {
            finSearch.value = '';
            const idx = sectors.value.findIndex(s => s.sector_code === code);
            if (idx >= 0) loadFinance(idx);
        }
        const latestFin = computed(() => {
            const d = financeData.value;
            if (!d || !d.finance || !d.finance.length) return null;
            const fin = d.finance;
            if (finQuarter.value === 'annual') {
                const latest = fin[fin.length - 1].report_date;
                const allYears = {};
                for (const f of fin) {
                    const yr = f.report_date.split('-')[0];
                    if (!allYears[yr]) allYears[yr] = [];
                    allYears[yr].push(f);
                }
                const sortedYears = Object.keys(allYears).sort();
                let targetYear = sortedYears[sortedYears.length - 1];
                if (allYears[targetYear].length < 4 && sortedYears.length > 1) {
                    targetYear = sortedYears[sortedYears.length - 2];
                }
                const yearData = allYears[targetYear];
                const total = { total_revenue: 0, total_net_profit: 0, revenue_growth: null, net_profit_growth: null, report_date: targetYear + '-12-31' };
                for (const f of yearData) {
                    total.total_revenue += f.total_revenue;
                    total.total_net_profit += f.total_net_profit;
                }
                const prevYear = String(Number(targetYear) - 1);
                const prevData = allYears[prevYear];
                if (prevData) {
                    let prevRev = 0, prevProfit = 0;
                    for (const f of prevData) { prevRev += f.total_revenue; prevProfit += f.total_net_profit; }
                    if (prevRev > 0) total.revenue_growth = Math.round((total.total_revenue - prevRev) / prevRev * 10000) / 100;
                    if (prevProfit > 0) total.net_profit_growth = Math.round((total.total_net_profit - prevProfit) / prevProfit * 10000) / 100;
                }
                return total;
            }
            return fin[fin.length - 1];
        });

        const currentPage = inject('currentPage');

        async function loadSectors() {
            loading.value = true;
            error.value = '';
            try {
                const r = await fetch(`${API_BASE}/strong/sectors?category=${category.value}&sort_by=${sortBy.value}&sort_order=${sortOrder.value}&prosperity=${prosperityFilter.value}&level=${industryLevel.value}&fin_quarter=${finQuarter.value}`);
                const data = await r.json();
                indexData.value = data.index;
                sectors.value = data.sectors;
                dates.value = data.dates;
            } catch (e) {
                error.value = '加载失败: ' + e.message;
            } finally {
                loading.value = false;
            }
        }

        async function loadChart() {
            chartLoading.value = true;
            try {
                const r = await fetch(`${API_BASE}/strong/index-kline?codes=${chartCodes.value.join(',')}&days=${chartDays.value}`);
                const data = await r.json();
                chartSeries.value = data.series;
                await nextTick();
                renderChart();
            } catch (e) {
                console.error(e);
            } finally {
                chartLoading.value = false;
            }
        }

        function renderChart() {
            const el = document.getElementById('strong-kline-chart');
            if (!el) return;
            if (el._chart) { el._chart.remove(); el._chart = null; }
            if (!chartSeries.value.length) return;

            const chart = LightweightCharts.createChart(el, {
                width: el.parentElement.clientWidth - 4,
                height: 360,
                layout: { background: { color: '#0a0e17' }, textColor: '#8e8ea0' },
                grid: { vertLines: { color: '#1e1e35' }, horzLines: { color: '#1e1e35' } },
                timeScale: { borderColor: '#2a2a40' },
                rightPriceScale: { borderColor: '#2a2a40' },
            });

            chartSeries.value.forEach((s, i) => {
                const color = CHART_COLORS[i % CHART_COLORS.length];
                if (s.type === 'index' || s.type === 'sector') {
                    const base = s.data.length > 0 ? s.data[0].close : 1;
                    const line = chart.addLineSeries({
                        color, lineWidth: 2, title: s.name,
                        lastValueVisible: true, priceLineVisible: false,
                    });
                    line.setData(s.data.map(d => ({ time: d.date, value: (d.close / base) * 100 })));
                }
            });
            chart.timeScale().fitContent();
            el._chart = chart;
        }

        function toggleSort(col) {
            if (sortBy.value === col) {
                sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc';
            } else {
                sortBy.value = col;
                sortOrder.value = 'desc';
            }
            loadSectors();
        }

        function sortArrow(col) {
            if (sortBy.value !== col) return '';
            return sortOrder.value === 'desc' ? ' ↓' : ' ↑';
        }

        function addChartCode(code) {
            if (chartCodes.value.length >= 5) return;
            if (!chartCodes.value.includes(code)) {
                chartCodes.value.push(code);
                loadChart();
            }
        }

        function removeChartCode(code) {
            if (code === '000001') return;
            chartCodes.value = chartCodes.value.filter(c => c !== code);
            loadChart();
        }

        function goToSector(code) {
            currentPage.value = 'strong_stocks';
            window._sectorCode = code;
        }

        async function loadFinance(index) {
            const s = sectors.value[index];
            if (!s) return;
            financeIndex.value = index;
            try {
                const r = await fetch(`${API_BASE}/strong/sector-finance?sector_code=${s.sector_code}`);
                financeData.value = await r.json();
                await nextTick();
                renderFinanceChart();
            } catch (e) {
                console.error(e);
            }
        }

        function prevFinance() {
            let i = financeIndex.value - 1;
            if (i < 0) i = sectors.value.length - 1;
            loadFinance(i);
        }

        function nextFinance() {
            let i = financeIndex.value + 1;
            if (i >= sectors.value.length) i = 0;
            loadFinance(i);
        }

        function renderFinanceChart() {
            const el = document.getElementById('finance-chart');
            if (!el || !financeData.value) return;
            if (el._chart) { el._chart.remove(); el._chart = null; }

            const kline = financeData.value.kline;
            const finance = financeData.value.finance;
            if (!kline.length) return;

            function filterQuarter(data) {
                if (finQuarter.value === 'annual') {
                    const yearMap = {};
                    for (const d of data) {
                        const yr = d.report_date.split('-')[0];
                        if (!yearMap[yr]) {
                            yearMap[yr] = { ...d, total_revenue: 0, total_net_profit: 0 };
                            yearMap[yr].report_date = yr + '-12-31';
                        }
                        yearMap[yr].total_revenue += d.total_revenue;
                        yearMap[yr].total_net_profit += d.total_net_profit;
                    }
                    return Object.values(yearMap).sort((a, b) => a.report_date.localeCompare(b.report_date));
                }
                const monthMap = { q1: 3, q2: 6, q3: 9 };
                const m = monthMap[finQuarter.value];
                return data.filter(d => parseInt(d.report_date.split('-')[1]) === m);
            }

            const chart = LightweightCharts.createChart(el, {
                width: el.parentElement.clientWidth - 4,
                height: 300,
                layout: { background: { color: '#0a0e17' }, textColor: '#8e8ea0' },
                grid: { vertLines: { color: '#1e1e35' }, horzLines: { color: '#1e1e35' } },
                timeScale: { borderColor: '#2a2a40' },
                rightPriceScale: { borderColor: '#2a2a40', scaleMargins: { top: 0.1, bottom: 0.1 } },
                leftPriceScale: { borderColor: '#22c55e44', scaleMargins: { top: 0.1, bottom: 0.1 }, visible: true },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            });

            const klineStart = kline[0].date;
            const finStart = finance.length > 0 ? finance[0].report_date : klineStart;
            const startDate = klineStart > finStart ? klineStart : finStart;
            const trimmedKline = kline.filter(d => d.date >= startDate);

            const filteredFinance = filterQuarter(finance).filter(d => d.report_date >= startDate);
            const finRange = filteredFinance.length > 0 ? filteredFinance : finance.filter(d => d.report_date >= startDate);

            const priceData = trimmedKline.map(d => ({ time: d.date, value: d.close }));
            const priceSeries = chart.addLineSeries({
                color: '#3b82f6', lineWidth: 2, title: '股价', lastValueVisible: true, priceLineVisible: false,
            });
            priceSeries.setData(priceData);

            let revSeries = null, profitSeries = null, revData = null, profitData = null;
            if (finRange.length > 0) {
                revSeries = chart.addLineSeries({
                    color: '#22c55e', lineWidth: 1.5, title: '营收', lastValueVisible: true, priceLineVisible: false,
                    priceScaleId: 'left',
                    lineType: LightweightCharts.LineType.WithSteps,
                });
                revData = finRange.map(d => ({ time: d.report_date, value: Math.round(d.total_revenue / 1e8) }));
                revSeries.setData(revData);
                profitSeries = chart.addLineSeries({
                    color: '#f59e0b', lineWidth: 1.5, title: '净利润', lastValueVisible: true, priceLineVisible: false,
                    priceScaleId: 'profit',
                    lineType: LightweightCharts.LineType.WithSteps,
                });
                chart.priceScale('profit').applyOptions({
                    scaleMargins: { top: 0.5, bottom: 0 },
                    borderColor: '#f59e0b44',
                });
                profitData = finRange.map(d => ({ time: d.report_date, value: Math.round(d.total_net_profit / 1e8) }));
                profitSeries.setData(profitData);
            }

            const tooltip = document.getElementById('finance-tooltip');
            chart.subscribeCrosshairMove((param) => {
                if (!param.time || !param.point || !tooltip) {
                    if (tooltip) tooltip.style.display = 'none';
                    return;
                }
                const t = param.time;
                function findVal(arr) {
                    if (!arr) return null;
                    let v = null;
                    for (const d of arr) {
                        if (d.time <= t) v = d;
                        else break;
                    }
                    return v;
                }
                const pv = findVal(priceData);
                const rv = findVal(revData);
                const pnv = findVal(profitData);
                let html = `<div style="color:#8e8ea0;margin-bottom:4px;">${t}</div>`;
                if (pv) html += `<div style="color:#3b82f6">● 股价 <b>${pv.value.toFixed(2)}</b></div>`;
                if (rv) html += `<div style="color:#22c55e">● 营收 <b>${rv.value}亿</b></div>`;
                if (pnv) html += `<div style="color:#f59e0b">● 净利润 <b>${pnv.value}亿</b></div>`;
                tooltip.innerHTML = html;
                tooltip.style.display = 'block';
                let left = param.point.x + 15;
                if (left + 160 > el.clientWidth) left = param.point.x - 165;
                tooltip.style.left = left + 'px';
                tooltip.style.top = Math.max(0, param.point.y - 20) + 'px';
            });

            chart.timeScale().fitContent();
            el._chart = chart;
        }

        function redrawFinance() {
            financeData.value = { ...financeData.value };
            nextTick(() => {
                const el = document.getElementById('finance-chart');
                if (el && el._chart) { el._chart.remove(); el._chart = null; }
                renderFinanceChart();
            });
        }

        onMounted(async () => {
            await loadSectors();
            loadChart();
            if (sectors.value.length) loadFinance(0);
        });

        return {
            indexData, sectors, loading, error, category, industryLevel, prosperityFilter, sortBy, sortOrder, dates,
            chartCodes, chartDays, chartSeries, chartLoading,
            financeData, financeIndex, finQuarter, latestFin, showFinCols,
            finSearch, filteredSectors, selectFinSector,
            loadSectors, loadChart, toggleSort, sortArrow,
            addChartCode, removeChartCode, goToSector,
            prevFinance, nextFinance, loadFinance, redrawFinance,
            fmt, fmtGrowth, fmtMoney, valClass,
        };
    },
});

app.component('strong-stocks-page', {
    template: '#strong-stocks-tpl',
    setup() {
        const _initSectorCode = window._sectorCode || '';
        const mode = ref(_initSectorCode ? 'c' : 'd');
        window._sectorCode = null;

        const sectorCode = ref('');
        const sectorData = ref(null);
        const indexRef = ref(null);
        const stocks = ref([]);
        const loading = ref(false);
        const error = ref('');
        const sortBy = ref('relative_ytd');
        const sortOrder = ref('desc');

        const selectedStocks = ref([]);
        const chartSeries = ref([]);
        const chartLoading = ref(false);
        const sectorFinData = ref(null);

        const topSectors = ref([]);
        const topCategory = ref('all');
        const topN = ref(3);

        const currentPage = inject('currentPage');

        async function loadStocks() {
            loading.value = true;
            error.value = '';
            try {
                const r = await fetch(`${API_BASE}/strong/sector-stocks?sector_code=${sectorCode.value}&sort_by=${sortBy.value}&sort_order=${sortOrder.value}`);
                const data = await r.json();
                sectorData.value = data.sector;
                indexRef.value = data.index_ref;
                stocks.value = data.stocks;
                if (selectedStocks.value.length === 0 && stocks.value.length >= 2) {
                    selectedStocks.value = stocks.value.slice(0, 2).map(s => s.stock_code);
                }
            } catch (e) {
                error.value = '加载失败: ' + e.message;
            } finally {
                loading.value = false;
            }
            try {
                const r2 = await fetch(`${API_BASE}/strong/sector-finance?sector_code=${sectorCode.value}`);
                sectorFinData.value = await r2.json();
            } catch (e) {
                sectorFinData.value = null;
            }
        }

        async function loadChart() {
            chartLoading.value = true;
            try {
                const codes = selectedStocks.value.join(',');
                const r = await fetch(`${API_BASE}/strong/stock-kline?sector_code=${sectorCode.value}&stock_codes=${codes}&days=120`);
                const data = await r.json();
                chartSeries.value = data.series;
                await nextTick();
                renderChart();
            } catch (e) {
                console.error(e);
            } finally {
                chartLoading.value = false;
            }
        }

        function renderChart() {
            const el = document.getElementById('stock-kline-chart');
            if (!el) return;
            if (el._chart) { el._chart.remove(); el._chart = null; }
            if (!chartSeries.value.length) return;

            const chart = LightweightCharts.createChart(el, {
                width: el.parentElement.clientWidth - 4,
                height: 320,
                layout: { background: { color: '#0a0e17' }, textColor: '#8e8ea0' },
                grid: { vertLines: { color: '#1e1e35' }, horzLines: { color: '#1e1e35' } },
                timeScale: { borderColor: '#2a2a40' },
                rightPriceScale: { borderColor: '#2a2a40' },
            });

            chartSeries.value.forEach((s, i) => {
                const color = CHART_COLORS[i % CHART_COLORS.length];
                const base = s.data.length > 0 ? s.data[0].close : 1;
                const line = chart.addLineSeries({
                    color, lineWidth: s.type === 'sector' ? 2 : 1.5,
                    title: s.name, lastValueVisible: true, priceLineVisible: false,
                });
                line.setData(s.data.map(d => ({ time: d.date, value: (d.close / base) * 100 })));
            });
            chart.timeScale().fitContent();
            el._chart = chart;
        }

        async function loadTopStocks() {
            loading.value = true;
            error.value = '';
            try {
                const r = await fetch(`${API_BASE}/strong/top-stocks?category=${topCategory.value}&top_n=${topN.value}`);
                const data = await r.json();
                topSectors.value = data.sectors;
            } catch (e) {
                error.value = '加载失败: ' + e.message;
            } finally {
                loading.value = false;
            }
        }

        function barWidth(relativeYtd, sec) {
            if (!sec.stocks.length || relativeYtd == null) return 0;
            const maxVal = Math.max(...sec.stocks.map(s => Math.abs(s.relative_ytd || 0)), 1);
            return Math.min(Math.abs(relativeYtd) / maxVal * 100, 100);
        }

        function openSectorStock(code, stockCode) {
            sectorCode.value = code;
            mode.value = 'c';
            selectedStocks.value = [stockCode];
            loadStocks().then(() => loadChart());
        }

        function toggleStock(code) {
            const idx = selectedStocks.value.indexOf(code);
            if (idx >= 0) {
                selectedStocks.value.splice(idx, 1);
            } else if (selectedStocks.value.length < 5) {
                selectedStocks.value.push(code);
            }
            loadChart();
        }

        function toggleSort(col) {
            if (sortBy.value === col) {
                sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc';
            } else {
                sortBy.value = col;
                sortOrder.value = 'desc';
            }
            loadStocks();
        }

        function sortArrow(col) {
            if (sortBy.value !== col) return '';
            return sortOrder.value === 'desc' ? ' ↓' : ' ↑';
        }

        function goBack() {
            if (mode.value === 'c' && !window._sectorCode) {
                mode.value = 'd';
                sectorData.value = null;
                stocks.value = [];
                loadTopStocks();
            } else {
                currentPage.value = 'strong';
            }
        }

        function goToStock(code) {
            currentPage.value = 'profile';
            window._profileStockCode = code;
        }

        onMounted(() => {
            if (mode.value === 'd') {
                loadTopStocks();
            } else {
                sectorCode.value = _initSectorCode;
                loadStocks().then(() => loadChart());
            }
        });

        return {
            mode, sectorCode, sectorData, indexRef, stocks, loading, error, sortBy, sortOrder,
            selectedStocks, chartSeries, chartLoading, sectorFinData,
            topSectors, topCategory, topN,
            loadStocks, loadChart, loadTopStocks, barWidth, openSectorStock,
            toggleStock, toggleSort, sortArrow, goBack, goToStock,
            fmt, fmtGrowth, fmtMoney, valClass, CHART_COLORS: window.CHART_COLORS,
        };
    },
});

app.component('data-catalog-page', {
    template: '#data-catalog-tpl',
    setup() {
        const currentPage = inject('currentPage');
        const q = ref('');
        const category = ref('全部');
        const sort = ref('table_name');
        const total = ref(0);
        const rows = ref([]);
        const loading = ref(false);
        const error = ref('');
        const refreshing = ref(false);

        const suggestions = ref([]);
        const suggestionIdx = ref(-1);
        let searchTimer = null;

        const categories = ['全部', '行情', '财务', '板块与股本', '预计算分析', '用户与日志'];
        const sortOptions = [
            { value: 'table_name', label: '按名称' },
            { value: 'latest_date', label: '按最新日期' },
            { value: 'row_count', label: '按行数' },
        ];

        const selectedTable = ref('');
        const detail = ref(null);
        const detailLoading = ref(false);
        const columns = ref([]);
        const columnsLoading = ref(false);

        async function loadList() {
            loading.value = true;
            error.value = '';
            try {
                const params = new URLSearchParams({
                    category: category.value === '全部' ? '' : category.value,
                    q: q.value.trim(),
                    sort: sort.value,
                });
                const r = await fetch(`${API_BASE}/governance/tables?${params}`);
                const d = await r.json();
                if (d.error) { error.value = d.error; return; }
                total.value = d.total || 0;
                rows.value = d.rows || [];
            } catch (e) {
                error.value = e.message;
            } finally {
                loading.value = false;
            }
        }

        async function onSearchInput() {
            const query = q.value.trim();
            if (query.length < 1) { suggestions.value = []; return; }
            if (searchTimer) clearTimeout(searchTimer);
            searchTimer = setTimeout(async () => {
                try {
                    const r = await fetch(`${API_BASE}/governance/tables/suggest?q=${encodeURIComponent(query)}`);
                    const d = await r.json();
                    suggestions.value = d.rows || [];
                    suggestionIdx.value = -1;
                } catch (e) {}
            }, 150);
        }

        function onSearchKeydown(e) {
            const len = suggestions.value.length;
            if (len === 0) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); suggestionIdx.value = Math.min(suggestionIdx.value + 1, len - 1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); suggestionIdx.value = Math.max(suggestionIdx.value - 1, 0); }
            else if (e.key === 'Enter' && suggestionIdx.value >= 0) {
                e.preventDefault();
                selectSuggestion(suggestions.value[suggestionIdx.value]);
            }
        }

        function onSearchEnter() {
            if (suggestionIdx.value >= 0) return;
            suggestions.value = [];
            loadList();
        }

        function selectSuggestion(s) {
            q.value = s.table_name;
            suggestions.value = [];
            suggestionIdx.value = -1;
            showDetail(s.table_name);
        }

        function clearSearch() {
            q.value = '';
            suggestions.value = [];
            loadList();
        }

        function setCategory(c) {
            category.value = c;
            loadList();
        }

        function setSort(s) {
            sort.value = s;
            loadList();
        }

        async function refreshMeta() {
            refreshing.value = true;
            try {
                await fetch(`${API_BASE}/governance/refresh`, { method: 'POST' });
                await loadList();
            } catch (e) {
                error.value = e.message;
            } finally {
                refreshing.value = false;
            }
        }

        async function showDetail(t) {
            selectedTable.value = t;
            detail.value = null;
            columns.value = [];
            detailLoading.value = true;
            columnsLoading.value = true;
            try {
                const r = await fetch(`${API_BASE}/governance/tables/${encodeURIComponent(t)}`);
                const d = await r.json();
                if (!d.error) detail.value = d;
            } catch (e) {}
            detailLoading.value = false;
            try {
                const r2 = await fetch(`${API_BASE}/governance/tables/${encodeURIComponent(t)}/columns`);
                const d2 = await r2.json();
                if (!d2.error) columns.value = d2.rows || [];
            } catch (e) {}
            columnsLoading.value = false;
        }

        function staleClass(r) {
            if (!r.latest_date) return '';
            const today = new Date();
            const d = new Date(r.latest_date);
            const diff = Math.floor((today - d) / (1000 * 60 * 60 * 24));
            if (diff <= 7) return 'dg-stale-new';
            if (diff <= 30) return 'dg-stale-warn';
            return 'dg-stale-old';
        }

        function goLineage(t) {
            window._lineageTable = t;
            window._lineageField = null;
            currentPage.value = 'data_lineage';
        }

        function goFieldLineage(t, col) {
            window._lineageTable = t;
            window._lineageField = col;
            currentPage.value = 'data_lineage';
        }

        onMounted(() => {
            loadList();
        });

        return {
            q, category, sort, total, rows, loading, error, refreshing,
            suggestions, suggestionIdx, categories, sortOptions,
            selectedTable, detail, detailLoading, columns, columnsLoading,
            onSearchInput, onSearchKeydown, onSearchEnter, selectSuggestion,
            clearSearch, setCategory, setSort, refreshMeta,
            showDetail, staleClass, goLineage, goFieldLineage,
        };
    },
});

app.component('data-lineage-page', {
    template: '#data-lineage-tpl',
    setup() {
        const currentPage = inject('currentPage');
        const tableInput = ref('');
        const activeView = ref('table');
        const currentTable = ref('');
        const currentField = ref('');
        const lineageData = ref(null);
        const fieldData = ref(null);
        const loading = ref(false);
        const error = ref('');
        const cyContainer = ref(null);
        let cy = null;

        const suggestions = ref([]);
        const suggestionIdx = ref(-1);
        let searchTimer = null;

        const clickedTableName = ref('');
        const clickedColumns = ref([]);
        const edgeTip = ref({ show: false, x: 0, y: 0, text: '' });

        const fieldUpstreamNotes = computed(() => {
            if (!fieldData.value || !fieldData.value.upstream.length) return '';
            const notes = fieldData.value.upstream.map(u => u.note).filter(n => n);
            return notes.length ? notes[0] : '';
        });

        function nodeColor(t) {
            if (t.startsWith('ads_stock')) return '#f59e0b';
            if (t.startsWith('ads_sector')) return '#7c3aed';
            if (t.startsWith('fin_') || t.startsWith('daily_kline') || t.startsWith('stock_') || t.startsWith('sector') || t === 'stocks') return '#1e3a5f';
            return '#475569';
        }

        function nodeTextColor(t) {
            if (t.startsWith('ads_stock')) return '#000';
            return '#e2e8f0';
        }

        function buildTableGraph(data) {
            const elements = [];
            const targetId = data.table;
            elements.push({
                data: { id: targetId, label: data.table_comment || targetId, enName: targetId, isTarget: true },
            });
            (data.upstream || []).forEach(u => {
                if (u.table === targetId) return; // 过滤自引用边
                elements.push({
                    data: { id: u.table, label: u.table_comment || u.table, enName: u.table, isUpstream: true },
                });
                elements.push({
                    data: { source: u.table, target: targetId, edges: u.edges || [] },
                });
            });
            (data.downstream || []).forEach(d => {
                elements.push({
                    data: { id: d.table, label: d.table_comment || d.table, enName: d.table, isDownstream: true },
                });
                elements.push({
                    data: { source: targetId, target: d.table },
                });
            });
            return elements;
        }

        function buildFieldGraph(data) {
            const elements = [];
            const centerId = `${data.table}.${data.field}`;
            elements.push({
                data: { id: centerId, label: data.field_comment || data.field, enName: `${data.table}.${data.field}`, isTarget: true },
            });
            (data.upstream || []).forEach(u => {
                const uid = `${u.source_table}.${u.source_field}`;
                elements.push({
                    data: { id: uid, label: `${u.source_field}\n${u.source_table}`, enName: uid, isUpstream: true, tableName: u.source_table },
                });
                elements.push({
                    data: { source: uid, target: centerId, transform: u.transform, formula: u.formula, note: u.note },
                });
            });
            (data.downstream || []).forEach(d => {
                const did = `${d.target_table}.${d.target_field}`;
                elements.push({
                    data: { id: did, label: `${d.target_field}\n${d.target_table}`, enName: did, isDownstream: true, tableName: d.target_table },
                });
                elements.push({
                    data: { source: centerId, target: did },
                });
            });
            return elements;
        }

        function renderGraph(elements, isField) {
            if (cy) { cy.destroy(); cy = null; }
            nextTick(() => {
                const el = cyContainer.value;
                if (!el || !window.cytoscape) return;
                const colorFn = isField
                    ? (n) => n.data('isTarget') ? '#00d4ff' : (n.data('isUpstream') ? '#f59e0b' : '#7c3aed')
                    : (n) => {
                        if (n.data('isTarget')) return '#00d4ff';
                        return nodeColor(n.data('enName') || n.id());
                    };
                const textColorFn = isField
                    ? (n) => n.data('isTarget') ? '#000' : '#e2e8f0'
                    : (n) => n.data('isTarget') ? '#000' : nodeTextColor(n.data('enName') || n.id());

                cy = window.cytoscape({
                    container: el,
                    elements,
                    style: [
                        {
                            selector: 'node',
                            style: {
                                'label': 'data(label)',
                                'text-valign': 'center',
                                'text-halign': 'center',
                                'text-wrap': 'wrap',
                                'text-max-width': '120px',
                                'font-size': '11px',
                                'color': '#e2e8f0',
                                'background-color': (n) => colorFn(n),
                                'border-width': (n) => n.data('isTarget') ? 3 : 1,
                                'border-color': (n) => n.data('isTarget') ? '#00d4ff' : 'rgba(255,255,255,0.2)',
                                'width': 80,
                                'height': 50,
                                'shape': 'round-rectangle',
                                'text-margin-y': 0,
                            },
                        },
                        {
                            selector: 'edge',
                            style: {
                                'width': 2,
                                'line-color': 'rgba(0,212,255,0.4)',
                                'target-arrow-color': 'rgba(0,212,255,0.6)',
                                'target-arrow-shape': 'triangle',
                                'curve-style': 'bezier',
                                'arrow-scale': 1.2,
                            },
                        },
                    ],
                    layout: {
                        name: 'breadthfirst',
                        directed: true,
                        padding: 30,
                        spacingFactor: 1.5,
                        animate: false,
                    },
                });
                cy.fit(undefined, 40);
                cy.on('tap', 'node', async (evt) => {
                    const node = evt.target;
                    const tableName = node.data('enName') || node.id();
                    if (isField) return;
                    const tid = tableName.split('.')[0];
                    clickedTableName.value = tid;
                    clickedColumns.value = [];
                    try {
                        const r = await fetch(`${API_BASE}/governance/tables/${encodeURIComponent(tid)}/columns`);
                        const d = await r.json();
                        if (!d.error) clickedColumns.value = d.rows || [];
                    } catch (e) {}
                });
                cy.on('mouseover', 'edge', (evt) => {
                    const edge = evt.target;
                    const pos = edge.renderedPosition();
                    let text = '';
                    const edges = edge.data('edges');
                    if (edges && edges.length) {
                        text = edges.slice(0, 4).map(e =>
                            `${e.target_column} ← ${e.transform || 'direct'}${e.formula ? ' | ' + e.formula : ''}`).join('\n');
                    } else if (edge.data('transform')) {
                        text = `转换: ${edge.data('transform')}`;
                        if (edge.data('formula')) text += `\n公式: ${edge.data('formula')}`;
                        if (edge.data('note')) text += `\n口径: ${edge.data('note')}`;
                    }
                    if (text) {
                        edgeTip.value = { show: true, x: pos.x, y: pos.y - 12, text };
                    }
                });
                cy.on('mouseout', 'edge', () => { edgeTip.value.show = false; });
                cy.on('pan zoom', () => { edgeTip.value.show = false; });
            });
        }

        async function loadTableLineage(t) {
            if (!t) return;
            activeView.value = 'table';
            currentTable.value = t;
            currentField.value = '';
            lineageData.value = null;
            fieldData.value = null;
            error.value = '';
            loading.value = true;
            try {
                const r = await fetch(`${API_BASE}/governance/lineage/table/${encodeURIComponent(t)}`);
                const d = await r.json();
                if (d.error) { error.value = d.error; loading.value = false; return; }
                lineageData.value = d;
                renderGraph(buildTableGraph(d), false);
            } catch (e) {
                error.value = e.message;
            } finally {
                loading.value = false;
            }
        }

        async function loadFieldLineage(t, col) {
            if (!t || !col) return;
            activeView.value = 'field';
            currentTable.value = t;
            currentField.value = col;
            lineageData.value = null;
            fieldData.value = null;
            error.value = '';
            loading.value = true;
            try {
                const r = await fetch(`${API_BASE}/governance/lineage/field/${encodeURIComponent(t)}/${encodeURIComponent(col)}`);
                const d = await r.json();
                if (d.error) { error.value = d.error; loading.value = false; return; }
                fieldData.value = d;
                renderGraph(buildFieldGraph(d), true);
            } catch (e) {
                error.value = e.message;
            } finally {
                loading.value = false;
            }
        }

        function goFieldView(t, col) {
            clickedColumns.value = [];
            loadFieldLineage(t, col);
        }

        function backToTableView() {
            if (currentTable.value) {
                loadTableLineage(currentTable.value);
            }
        }

        function fitGraph() {
            if (cy) cy.fit(undefined, 40);
        }

        function reloadGraph() {
            if (activeView.value === 'table' && currentTable.value) {
                loadTableLineage(currentTable.value);
            } else if (activeView.value === 'field' && currentTable.value && currentField.value) {
                loadFieldLineage(currentTable.value, currentField.value);
            }
        }

        async function onSearchInput() {
            const query = tableInput.value.trim();
            if (query.length < 1) { suggestions.value = []; return; }
            if (searchTimer) clearTimeout(searchTimer);
            searchTimer = setTimeout(async () => {
                try {
                    const r = await fetch(`${API_BASE}/governance/tables/suggest?q=${encodeURIComponent(query)}`);
                    const d = await r.json();
                    suggestions.value = d.rows || [];
                    suggestionIdx.value = -1;
                } catch (e) {}
            }, 150);
        }

        function onSearchKeydown(e) {
            const len = suggestions.value.length;
            if (len === 0) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); suggestionIdx.value = Math.min(suggestionIdx.value + 1, len - 1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); suggestionIdx.value = Math.max(suggestionIdx.value - 1, 0); }
            else if (e.key === 'Enter' && suggestionIdx.value >= 0) {
                e.preventDefault();
                selectSuggestion(suggestions.value[suggestionIdx.value]);
            }
        }

        function onSearchEnter() {
            if (suggestionIdx.value >= 0) return;
            suggestions.value = [];
            loadTableLineage(tableInput.value.trim());
        }

        function selectSuggestion(s) {
            tableInput.value = s.table_name;
            suggestions.value = [];
            suggestionIdx.value = -1;
            loadTableLineage(s.table_name);
        }

        onMounted(() => {
            if (window._lineageTable) {
                tableInput.value = window._lineageTable;
                if (window._lineageField) {
                    loadFieldLineage(window._lineageTable, window._lineageField);
                } else {
                    loadTableLineage(window._lineageTable);
                }
                window._lineageTable = null;
                window._lineageField = null;
            }
        });

        onUnmounted(() => {
            if (cy) { cy.destroy(); cy = null; }
        });

        return {
            tableInput, activeView, currentTable, currentField,
            lineageData, fieldData, loading, error, cyContainer,
            suggestions, suggestionIdx,
            clickedTableName, clickedColumns, fieldUpstreamNotes, edgeTip,
            onSearchInput, onSearchKeydown, onSearchEnter, selectSuggestion,
            loadTableLineage, goFieldView, backToTableView, fitGraph, reloadGraph,
        };
    },
});

app.component('placeholder-page', {
    props: ['page'],
    template: '<div class="placeholder"><div class="big-icon">{{ icon }}</div><p>{{ page.label }}</p><p>功能开发中...</p></div>',
    computed: {
        icon() { return this.page.icon || '⊡'; },
    },
});

app.mount('#app');

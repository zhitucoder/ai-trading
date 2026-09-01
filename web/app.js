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

function receivableClass(val, threshold) {
    if (val == null) return '';
    return val < threshold ? 'up-highlight' : '';
}

const app = createApp({
    setup() {
        const currentPage = ref('profile');
        const pages = [
            { id: 'strong', label: '强势板块', icon: '▲' },
            { id: 'strong_stocks', label: '强势个股', icon: '★' },
            { id: 'screening', label: '选股策略', icon: '⊞' },
            { id: 'vcp', label: 'VCP波动收缩', icon: '◐' },
            { id: 'bt_strategies', label: '回测策略', icon: '⇄' },
            { id: 'profile', label: '股票画像', icon: '◈' },
            { id: 'dividend', label: '分红列表', icon: '❖' },
            { id: 'buyback', label: '股份回购', icon: '↺' },
            { id: 'debate', label: 'AI多空辩论', icon: '⚖' },
            { id: 'expert', label: '蒸馏专家', icon: '⚗' },
            { id: 'dmdl', label: '估值榜', icon: '⚖' },
            { id: 'query', label: '智能问数', icon: '✦' },
            { id: 'data_mgmt', label: '数据管理', icon: '⚙' },
            { id: 'data_catalog', label: '数据资产', icon: '🗂' },
            { id: 'data_lineage', label: '数据血缘', icon: '⛓' },
            { id: 'fund', label: '基金持仓', icon: '◈' },
            { id: 'institution', label: '国家队持仓', icon: '🏛' },
            { id: 'logic', label: '投资逻辑', icon: '⛓' },
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
        const activeTab = ref('screening');
        const currentPage = inject('currentPage');
        const returnPage = ref('');

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
        const marginChartCanvas = ref(null);
        const marginChartLoading = ref(false);

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
                    loadMarginChart();
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

        async function loadMarginChart() {
            if (!stockCode.value) return;
            marginChartLoading.value = true;
            try {
                const r = await fetch(`${API_BASE}/profile/${stockCode.value}/margin-chart`);
                const data = await r.json();
                if (data.margin && data.margin.length) renderMarginChart(data);
            } catch (e) {}
            finally { marginChartLoading.value = false; }
        }

        function renderMarginChart(data) {
            const canvas = marginChartCanvas.value;
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
            const pad = { top: 30*dpr, bottom: 30*dpr, left: 60*dpr, right: 60*dpr };
            const cw = W - pad.left - pad.right, ch = H - pad.top - pad.bottom;

            ctx.clearRect(0, 0, W, H);

            const marginData = data.margin;
            const klineData = data.kline;

            const rzyeMax = Math.max(...marginData.map(m => m.rzye)) * 1.15 || 1;
            const rqyeMax = Math.max(...marginData.map(m => m.rqye)) * 1.15 || 1;
            const priceMax = Math.max(...klineData.map(k => k.close)) * 1.15 || 1;

            function yRzye(v) { return pad.top + ch * (1 - v / rzyeMax); }
            function yRqye(v) { return pad.top + ch * (1 - v / rqyeMax); }
            function yPrice(v) { return pad.top + ch * (1 - v / priceMax); }

            const allDates = [...new Set([...marginData.map(m => m.date), ...klineData.map(k => k.date)])].sort();
            const dateMap = {};
            allDates.forEach((d, i) => dateMap[d] = i);
            const xStep = allDates.length > 1 ? cw / (allDates.length - 1) : cw;
            function dateToX(dateStr) { return pad.left + (dateMap[dateStr] || 0) * xStep; }

            ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 1*dpr;
            for (let i = 0; i <= 4; i++) {
                const y = pad.top + ch * i / 4;
                ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + cw, y); ctx.stroke();
            }

            if (klineData.length > 1) {
                ctx.beginPath(); ctx.strokeStyle = '#4ecdc4'; ctx.lineWidth = 2*dpr;
                for (let i = 0; i < klineData.length; i++) {
                    const x = dateToX(klineData[i].date);
                    const y = yPrice(klineData[i].close);
                    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                }
                ctx.stroke();
            }

            if (marginData.length > 1) {
                ctx.beginPath(); ctx.strokeStyle = '#6495ed'; ctx.lineWidth = 2*dpr;
                for (let i = 0; i < marginData.length; i++) {
                    const x = dateToX(marginData[i].date);
                    const y = yRzye(marginData[i].rzye);
                    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                }
                ctx.stroke();
            }

            if (marginData.length > 1) {
                ctx.beginPath(); ctx.strokeStyle = '#ffd700'; ctx.lineWidth = 2*dpr;
                for (let i = 0; i < marginData.length; i++) {
                    const x = dateToX(marginData[i].date);
                    const y = yRqye(marginData[i].rqye);
                    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                }
                ctx.stroke();
            }

            ctx.fillStyle = '#666'; ctx.font = `${10*dpr}px sans-serif`; ctx.textAlign = 'right';
            for (let i = 0; i <= 4; i++) {
                const v = (rzyeMax * i / 4).toFixed(0);
                ctx.fillText(v + '亿', pad.left - 6*dpr, pad.top + ch * (1 - i/4) + 4*dpr);
            }

            ctx.textAlign = 'left';
            for (let i = 0; i <= 4; i++) {
                const v = (priceMax * i / 4).toFixed(0);
                ctx.fillText(v + '元', pad.left + cw + 6*dpr, pad.top + ch * (1 - i/4) + 4*dpr);
            }

            if (allDates.length > 0) {
                ctx.fillStyle = '#999'; ctx.font = `${11*dpr}px sans-serif`; ctx.textAlign = 'center';
                const showCount = Math.min(6, allDates.length);
                for (let i = 0; i < showCount; i++) {
                    const idx = Math.floor(i * (allDates.length - 1) / (showCount - 1));
                    const x = dateToX(allDates[idx]);
                    const label = allDates[idx].substring(0, 4) + '-' + allDates[idx].substring(4, 6);
                    ctx.fillText(label, x, H - pad.bottom + 16*dpr);
                }
            }

            const legend = [
                {label:'股价',color:'#4ecdc4'},{label:'融资余额',color:'#6495ed'},
                {label:'融券余额',color:'#ffd700'},
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

            const chartData = { marginData, klineData, allDates, dateToX, yRzye, yRqye, yPrice, pad, cw, ch, dpr };
            canvas.chartData = chartData;

            canvas.onmousemove = function(e) {
                const cr = canvas.getBoundingClientRect();
                const mx = (e.clientX - cr.left) * dpr;
                const cd = canvas.chartData;
                if (!cd) return;

                let closestMargin = null, minMDist = Infinity;
                for (const m of cd.marginData) {
                    const x = dateToX(m.date);
                    const dist = Math.abs(mx - x);
                    if (dist < minMDist) { minMDist = dist; closestMargin = m; }
                }
                let closestKline = null, minKDist = Infinity;
                for (const k of cd.klineData) {
                    const x = dateToX(k.date);
                    const dist = Math.abs(mx - x);
                    if (dist < minKDist) { minKDist = dist; closestKline = k; }
                }

                const bestDist = Math.min(minMDist, minKDist);
                if (bestDist > cw / cd.allDates.length * 2) { tooltip.style.display = 'none'; return; }

                const displayDate = closestMargin ? closestMargin.date : (closestKline ? closestKline.date : null);
                if (!displayDate) { tooltip.style.display = 'none'; return; }

                const klinePoint = closestKline;
                const marginPoint = closestMargin;

                let html = `<div style="color:#4ecdc4;font-weight:700;margin-bottom:4px;">${displayDate.substring(0,4)}-${displayDate.substring(4,6)}-${displayDate.substring(6,8)}</div>`;
                if (klinePoint) html += `<div><span style="color:#4ecdc4;">股价</span> ${klinePoint.close.toFixed(2)}元</div>`;
                if (marginPoint) {
                    html += `<div><span style="color:#6495ed;">融资余额</span> ${marginPoint.rzye.toFixed(2)}亿</div>`;
                    html += `<div><span style="color:#ffd700;">融券余额</span> ${marginPoint.rqye.toFixed(2)}亿</div>`;
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

        function goBack() {
            if (returnPage.value) {
                const p = returnPage.value;
                returnPage.value = '';
                currentPage.value = p;
            }
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
        const filterReceivableToRevMin = ref(null);
        const filterReceivableToRevMax = ref(null);
        const filterReceivableToAssetsMin = ref(null);
        const filterReceivableToAssetsMax = ref(null);
        const filterRoeMin = ref(null);
        const filterRoeMax = ref(null);
        const filterNetMarginMin = ref(null);
        const filterNetMarginMax = ref(null);
        const filterGm2025Min = ref(null);
        const filterGm2025Max = ref(null);
        const filterNetMargin2025Min = ref(null);
        const filterNetMargin2025Max = ref(null);
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
        const filterFundRecent8UpMin = ref(null);
        const filterFundRecent8NetMin = ref(null);
        const filterFundRecent6UpMin = ref(null);
        const filterFundRecent4UpMin = ref(null);
        const filterFundConsecGrowthMin = ref(null);
        const filterFundConsecDeclineMin = ref(null);
        const filterRecent2qFundCountMin = ref(null);
        const filterRecent2qFundCountMax = ref(null);
        const filterRecent4qFundCountMin = ref(null);
        const filterRecent4qFundCountMax = ref(null);
        const filterRecent1qFundCountMin = ref(null);
        const filterRecent1qFundCountMax = ref(null);
        const filterRecent8qAmountMin = ref(null);
        const filterFundHoldingGrowthMin = ref(null);
        const filterFundHoldingGrowthMax = ref(null);
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
                selectedZxmFilters.value[field] = { [val]: true };
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
                        if (keys.length) zxmBody[f.field] = keys[0];
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
                    receivable_to_revenue_min: filterReceivableToRevMin.value || null,
                    receivable_to_revenue_max: filterReceivableToRevMax.value || null,
                    receivable_to_assets_min: filterReceivableToAssetsMin.value || null,
                    receivable_to_assets_max: filterReceivableToAssetsMax.value || null,
                    roe_min: filterRoeMin.value || null,
                    roe_max: filterRoeMax.value || null,
                    net_margin_min: filterNetMarginMin.value || null,
                    net_margin_max: filterNetMarginMax.value || null,
                    gm_2025_min: filterGm2025Min.value || null,
                    gm_2025_max: filterGm2025Max.value || null,
                    net_margin_2025_min: filterNetMargin2025Min.value || null,
                    net_margin_2025_max: filterNetMargin2025Max.value || null,
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
                    fund_recent8_up_min: filterFundRecent8UpMin.value || null,
                    fund_recent8_net_min: filterFundRecent8NetMin.value || null,
                    fund_recent6_up_min: filterFundRecent6UpMin.value || null,
                    fund_recent4_up_min: filterFundRecent4UpMin.value || null,
                    fund_consec_growth_min: filterFundConsecGrowthMin.value || null,
                    fund_consec_decline_min: filterFundConsecDeclineMin.value || null,
                    recent2q_fund_count_min: filterRecent2qFundCountMin.value || null,
                    recent2q_fund_count_max: filterRecent2qFundCountMax.value || null,
                    recent4q_fund_count_min: filterRecent4qFundCountMin.value || null,
                    recent4q_fund_count_max: filterRecent4qFundCountMax.value || null,
                    recent1q_fund_count_min: filterRecent1qFundCountMin.value || null,
                    recent1q_fund_count_max: filterRecent1qFundCountMax.value || null,
                    recent8q_amount_min: filterRecent8qAmountMin.value != null ? filterRecent8qAmountMin.value * 1e8 : null,
                    fund_holding_growth_min: filterFundHoldingGrowthMin.value || null,
                    fund_holding_growth_max: filterFundHoldingGrowthMax.value || null,
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
            filterReceivableToRevMin.value = null;
            filterReceivableToRevMax.value = null;
            filterReceivableToAssetsMin.value = null;
            filterReceivableToAssetsMax.value = null;
            filterRoeMin.value = null;
            filterRoeMax.value = null;
            filterNetMarginMin.value = null;
            filterNetMarginMax.value = null;
            filterGm2025Min.value = null;
            filterGm2025Max.value = null;
            filterNetMargin2025Min.value = null;
            filterNetMargin2025Max.value = null;
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
            filterFundRecent8UpMin.value = null;
            filterFundRecent8NetMin.value = null;
            filterFundRecent6UpMin.value = null;
            filterFundRecent4UpMin.value = null;
            filterFundConsecGrowthMin.value = null;
            filterFundConsecDeclineMin.value = null;
            filterRecent2qFundCountMin.value = null;
            filterRecent2qFundCountMax.value = null;
            filterRecent4qFundCountMin.value = null;
            filterRecent4qFundCountMax.value = null;
            filterRecent1qFundCountMin.value = null;
            filterRecent1qFundCountMax.value = null;
            filterRecent8qAmountMin.value = null;
            filterFundHoldingGrowthMin.value = null;
            filterFundHoldingGrowthMax.value = null;
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
            if (window._profileReturnPage) {
                returnPage.value = window._profileReturnPage;
                window._profileReturnPage = null;
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
            activeTab, stockCode, loading, profile, error, finChartLoading, finChartCanvas, fundChartLoading, fundChartImg, fundChartImgEl, divChartCanvas, marginChartCanvas, marginChartLoading,
            loadProfile, loadFinChart, loadFundChart, loadDivChart, loadMarginChart, scoreClass, scoreTextClass, rsiClass, debtClass, gmTrendClass, goToProfile, goBack, currentPage, returnPage, introStatusName, chainName,
            stageOptions, selectedStages, filterTechScore, filterFundScore,
            filterRevGrowth, filterProfitGrowth, filterDebtMax,
            filterPrevYearProfitMin, filterPrevYearProfitMax, filterCurQuarterProfitMin, filterCurQuarterProfitMax,
            filterGmGrowthQ, filterGmGrowth2y,
            filterContractLiabMin, filterContractLiabMax,
            filterReceivableToRevMin, filterReceivableToRevMax, filterReceivableToAssetsMin, filterReceivableToAssetsMax,
            filterRoeMin, filterRoeMax, filterRoeTtmMin, filterRoeTtmMax,
            filterPeMax, filterPegMax,
            filterNetMarginMin, filterNetMarginMax, filterMarketCapRange, marketCapRanges,
            filterGm2025Min, filterGm2025Max, filterNetMargin2025Min, filterNetMargin2025Max,
            filterDividendYieldMin, filterDividendYieldMax,
            filterHasDivThisYear, filterHasMidYear, filterConsecutiveDivYears,
            filterFundRecent8UpMin, filterFundRecent8NetMin, filterFundRecent6UpMin, filterFundRecent4UpMin,
            filterFundConsecGrowthMin, filterFundConsecDeclineMin,
            filterRecent2qFundCountMin, filterRecent2qFundCountMax,
            filterRecent4qFundCountMin, filterRecent4qFundCountMax,
            filterRecent1qFundCountMin, filterRecent1qFundCountMax,
            filterRecent8qAmountMin, filterFundHoldingGrowthMin, filterFundHoldingGrowthMax,
            filterRevCagr3yMin, filterRevCagr3yMax, filterRevCagr5yMin, filterRevCagr5yMax,
            filterProfitCagr3yMin, filterProfitCagr3yMax, filterProfitCagr5yMin, filterProfitCagr5yMax,
            growthTagOptions, selectedGrowthTags,
            zxmFilterOptions, selectedZxmFilters, toggleZxmFilter, isZxmFilterActive, hasActiveZxmFilter,
            searchLoading, searchResult, profileStatusData, sortBy, sortOrder,
            refreshing, refreshProgress, refreshToast,
            sectorListIndustries, sectorListConcepts, selectedSectors, toggleSector,
            toggleStage, toggleGrowthTag, onFilterChange, doSearch, resetFilters, triggerRefresh,
            toggleSort, sortArrow,
            fmt, fmtGrowth, fmtMoney, valClass, receivableClass,
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
        const source = ref('eastmoney');

        async function loadList() {
            loading.value = true;
            error.value = '';
            try {
                const endpoint = source.value === 'tushare' ? '/dividends/tushare/list' : '/dividends/list';
                const params = new URLSearchParams({
                    year: year.value || '', sort: sort.value, order: order.value,
                    page: page.value, page_size: pageSize.value,
                });
                if (source.value === 'eastmoney') params.set('is_mid', isMid.value);
                const r = await fetch(`${API_BASE}${endpoint}?${params}`);
                const d = await r.json();
                if (d.error) error.value = d.error;
                else { rows.value = d.rows; total.value = d.total; }
            } catch (e) { error.value = e.message; } finally { loading.value = false; }
        }

        function switchSource(src) {
            if (source.value === src) return;
            source.value = src;
            page.value = 1;
            loadList();
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

        function tsToCode(ts_code) {
            return (ts_code || '').split('.')[0];
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
        return { years, year, isMid, sort, order, page, pageSize, total, rows, loading, error, source, switchSource, loadList, toggleSort, sortArrow, goStock, tsToCode, onFilter, yieldTip, payoutTip, planWidth, startResize };
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

// ── 股份回购 ──
app.component('buyback-page', {
    template: '#buyback-tpl',
    setup() {
        const currentPage = inject('currentPage');
        const keyword = ref('');
        const purpose = ref('');
        const progressStatus = ref('');
        const sort = ref('notice_date');
        const order = ref('desc');
        const page = ref(1);
        const pageSize = ref(50);
        const total = ref(0);
        const rows = ref([]);
        const loading = ref(false);
        const error = ref('');
        const tip = reactive({ show: false, text: '', x: 0, y: 0 });
        let kwTimer = null;

        async function loadList() {
            loading.value = true;
            error.value = '';
            try {
                const params = new URLSearchParams({
                    keyword: keyword.value || '', purpose: purpose.value || '',
                    progress_status: progressStatus.value || '',
                    sort: sort.value, order: order.value,
                    page: page.value, page_size: pageSize.value,
                });
                const r = await fetch(`${API_BASE}/buyback/list?${params}`);
                const d = await r.json();
                if (d.error) error.value = d.error;
                else {
                    rows.value = d.rows;
                    total.value = d.total;
                }
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
            window._profileReturnPage = 'buyback';
            window._profileStockCode = code;
            currentPage.value = 'profile';
        }

        function onFilter() { page.value = 1; loadList(); }

        function onKeywordInput() {
            clearTimeout(kwTimer);
            kwTimer = setTimeout(() => { page.value = 1; loadList(); }, 350);
        }

        function showTip(e, text) {
            if (!text) return;
            tip.text = text;
            tip.x = e.clientX + 14;
            tip.y = e.clientY + 14;
            tip.show = true;
        }
        function moveTip(e) {
            if (!tip.show) return;
            tip.x = e.clientX + 14;
            tip.y = e.clientY + 14;
        }
        function hideTip() { tip.show = false; }

        function fmtInt(v) {
            if (v == null) return '-';
            return Number(v).toLocaleString('zh-CN');
        }
        function fmtAmt(v) {
            if (v == null) return '-';
            return (Number(v) / 1e8).toFixed(2) + '亿';
        }
        function qtyText(r) {
            if (r.repur_num_lower != null || r.repur_num_cap != null)
                return fmtInt(r.repur_num_lower) + ' ~ ' + fmtInt(r.repur_num_cap);
            return fmtInt(r.repur_num);
        }
        function amtText(r) {
            if (r.repur_amount_lower != null || r.repur_amount_limit != null)
                return fmtAmt(r.repur_amount_lower) + ' ~ ' + fmtAmt(r.repur_amount_limit);
            return fmtAmt(r.repur_amount);
        }
        function periodText(r) {
            return (r.repur_start_date || '-') + ' ~ ' + (r.repur_end_date || '-');
        }
        function progClass(p) {
            if (p === '004' || p === '006' || p === '008') return 'bb-done';
            if (p === '003' || p === '007') return 'bb-doing';
            if (p === '005') return 'bb-stop';
            return 'bb-plan';
        }

        onMounted(loadList);

        return {
            keyword, purpose, progressStatus, sort, order, page, pageSize, total, rows, loading, error, tip,
            loadList, toggleSort, sortArrow, goStock, onFilter, onKeywordInput,
            showTip, moveTip, hideTip, fmtInt, fmtAmt, progClass,
        };
    },
});

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
        const status = ref({ kline: {}, financial: {}, sector: {}, institution: {} });
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

        const instLoading = ref(false);
        const instResult = ref('');
        const instError = ref('');

        const instDotClass = computed(() => {
            return instLoading.value ? 'dm-dot-sync' : ((status.value.institution?.inst_stock > 0) ? 'dm-dot-online' : 'dm-dot-pending');
        });
        const instStatusText = computed(() => {
            return instLoading.value ? '计算中' : (status.value.institution?.status === 'running' ? '运行中' : ((status.value.institution?.inst_stock > 0) ? '已计算' : '待计算'));
        });

        async function updateInstitution() {
            instLoading.value = true;
            instResult.value = '';
            instError.value = '';
            try {
                const r = await fetch(`${API_BASE}/data/update-institution-ads`, { method: 'POST' });
                const data = await r.json();
                if (data.status === 'running') {
                    instResult.value = '国家队持仓预计算任务已在执行中';
                } else if (data.status === 'error') {
                    instError.value = data.message || '计算失败';
                } else {
                    instResult.value = data.message || '国家队持仓预计算已启动';
                }
                setTimeout(loadStatus, 1500);
            } catch (e) {
                instError.value = e.message;
            } finally {
                instLoading.value = false;
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
            instLoading, instResult, instError, instDotClass, instStatusText, updateInstitution,
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

app.component('fund-page', {
    template: '#fund-tpl',
    setup() {
        const tab = ref('macro');
        const loading = ref(false);
        const error = ref('');
        const macroData = ref(null);
        const sectorType = ref('industry');
        const sectorList = ref([]);
        const selectedSector = ref('');
        const sectorStocks = ref([]);
        const stockInput = ref('');
        const stockDetail = ref(null);
        const stockSuggestions = ref([]);
        const stockSuggestionIdx = ref(-1);
        let searchTimer = null;
        const stockHoldings = ref({ rows: [], total: 0, offset: 0 });
        const holdingsSort = ref({ key: 'mkv', dir: 'desc' });
        const holdingsLoading = ref(false);
        const fundModal = ref(null);
        const screenType = ref('thousand');
        const screenResult = ref([]);
        const latestQuarter = ref('');

        async function loadMacro() {
            loading.value = true;
            error.value = '';
            try {
                const res = await fetch(`${API_BASE}/fund/macro/overview`);
                macroData.value = await res.json();
                latestQuarter.value = macroData.value.latest_date || '';
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        async function loadSectorFlow() {
            loading.value = true;
            try {
                const res = await fetch(`${API_BASE}/fund/sector/flow?sector_type=${sectorType.value}`);
                sectorList.value = await res.json();
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        async function loadSectorStocks(name) {
            selectedSector.value = name;
            loading.value = true;
            try {
                const res = await fetch(`${API_BASE}/fund/sector/${encodeURIComponent(name)}/stocks`);
                sectorStocks.value = await res.json();
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        async function loadStockDetail(code) {
            if (!code) return;
            loading.value = true;
            error.value = '';
            try {
                const res = await fetch(`${API_BASE}/fund/stock/${code}`);
                stockDetail.value = await res.json();
                await loadHoldings(code, 0, true);
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        async function loadHoldings(code, offset, reset = false) {
            const c = code || stockInput.value;
            if (!c) return;
            holdingsLoading.value = true;
            try {
                const { key, dir } = holdingsSort.value;
                const url = `${API_BASE}/fund/stock/${c}/holdings?offset=${offset}&limit=20&sort_key=${key}&sort_dir=${dir}`;
                const res = await fetch(url);
                const data = await res.json();
                if (reset) {
                    stockHoldings.value = { ...data, rows: data.rows };
                } else {
                    stockHoldings.value = { ...data, rows: [...(stockHoldings.value.rows || []), ...data.rows] };
                }
            } catch (e) { error.value = e.message; }
            holdingsLoading.value = false;
        }

        function loadMoreHoldings() {
            if (!stockHoldings.value.total || stockHoldings.value.rows.length >= stockHoldings.value.total) return;
            loadHoldings(stockInput.value, stockHoldings.value.rows.length, false);
        }

        async function onStockInput() {
            const q = stockInput.value.trim();
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
            if (!code) return;
            stockInput.value = code;
            stockSuggestions.value = [];
            stockSuggestionIdx.value = -1;
            loadStockDetail(code);
        }

        function sortHoldings(key) {
            if (holdingsSort.value.key === key) {
                holdingsSort.value = { key, dir: holdingsSort.value.dir === 'asc' ? 'desc' : 'asc' };
            } else {
                holdingsSort.value = { key, dir: 'desc' };
            }
            loadHoldings(stockInput.value, 0, true);
        }

        function sortArrowH(key) {
            if (holdingsSort.value.key !== key) return '';
            return holdingsSort.value.dir === 'asc' ? ' ▲' : ' ▼';
        }

        async function openFundHistory(h) {
            if (!h || !h.fund_code) return;
            fundModal.value = { fund_code: h.fund_code, fund_name: h.fund_name, rows: [], loading: true };
            try {
                const res = await fetch(`${API_BASE}/fund/stock/${stockInput.value}/fund/${h.fund_code}`);
                const data = await res.json();
                fundModal.value = { fund_code: data.fund_code, fund_name: data.fund_name, rows: data.rows || [], loading: false };
                await nextTick();
                renderFundHistoryChart(data.rows || []);
            } catch (e) {
                fundModal.value.rows = [];
                fundModal.value.loading = false;
            }
        }

        function renderFundHistoryChart(rows) {
            const el = document.getElementById('fund-hist-chart');
            if (!el) return;
            if (el._chart) { el._chart.remove(); el._chart = null; }
            if (!rows.length) return;

            const chart = LightweightCharts.createChart(el, {
                width: el.clientWidth,
                height: el.clientHeight || 300,
                layout: { background: { color: 'transparent' }, textColor: '#8e8ea0' },
                grid: { vertLines: { color: '#1e1e35' }, horzLines: { color: '#1e1e35' } },
                timeScale: { borderColor: '#2a2a40', timeVisible: false },
                rightPriceScale: { borderColor: '#2a2a40' },
                leftPriceScale: { borderColor: '#2a2a40', visible: true },
            });

            const ts = d => `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
            const toWan = v => (v / 10000);

            const amount = chart.addLineSeries({
                color: '#3b82f6', lineWidth: 2, title: '持仓股数(万股)',
                priceLineVisible: false, priceScaleId: 'amount',
            });
            amount.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.55 } });
            amount.setData(rows.filter(r => r.amount != null).map(r => ({ time: ts(r.end_date), value: toWan(r.amount) })));

            const mkv = chart.addLineSeries({
                color: '#f0b90b', lineWidth: 2, title: '持仓市值(亿元)',
                priceLineVisible: false, priceScaleId: 'mkv',
            });
            mkv.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.55 }, visible: true });
            mkv.setData(rows.filter(r => r.mkv != null).map(r => ({ time: ts(r.end_date), value: r.mkv / 1e8 })));

            const ratio = chart.addLineSeries({
                color: '#22c55e', lineWidth: 2, title: '占基金净值比%',
                priceLineVisible: false, priceScaleId: 'ratio',
            });
            ratio.priceScale().applyOptions({ scaleMargins: { top: 0.58, bottom: 0.05 }, visible: true });
            ratio.setData(rows.filter(r => r.stk_mkv_ratio != null).map(r => ({ time: ts(r.end_date), value: r.stk_mkv_ratio })));

            chart.timeScale().fitContent();
            el._chart = chart;
        }

        function closeFundModal() {
            const el = document.getElementById('fund-hist-chart');
            if (el && el._chart) { el._chart.remove(); el._chart = null; }
            fundModal.value = null;
        }

        function fmtShares(amount) {
            if (amount == null) return '-';
            return (amount / 10000).toFixed(2);
        }

        function fmtPct(val) {
            if (val == null || val === '') return '-';
            return Number(val).toFixed(2) + '%';
        }

        function fundHoldRatio(h) {
            if (h == null || h.total_amount == null || !h.total_shares) return null;
            return h.total_amount / h.total_shares * 100;
        }

        async function loadScreen() {
            loading.value = true;
            try {
                const res = await fetch(`${API_BASE}/fund/screen?type=${screenType.value}`);
                screenResult.value = await res.json();
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        function onTabChange(t) {
            tab.value = t;
            if (t === 'macro') loadMacro();
            else if (t === 'sector') loadSectorFlow();
            else if (t === 'screen') loadScreen();
        }

        function signalColor(s) {
            return s === 'A' ? '#ef4444' : s === 'B' ? '#f59e0b' : s === 'C' ? '#3b82f6' : '#22c55e';
        }
        function signalText(s) {
            return s === 'A' ? '加速流入' : s === 'B' ? '减速流入' : s === 'C' ? '减速流出' : '加速流出';
        }

        onMounted(() => loadMacro());

        return {
            tab, loading, error, macroData, sectorType, sectorList,
            selectedSector, sectorStocks, stockInput, stockDetail,
            stockSuggestions, stockSuggestionIdx, stockHoldings,
            holdingsSort, holdingsLoading, fundModal,
            screenType, screenResult, latestQuarter,
            onTabChange, loadMacro, loadSectorFlow, loadSectorStocks,
            loadStockDetail, loadScreen, signalColor, signalText,
            onStockInput, onStockKeydown, selectStock,
            sortHoldings, sortArrowH, fmtShares, fmtPct, fundHoldRatio,
            loadMoreHoldings, openFundHistory, closeFundModal,
            fmtMoney, fmtGrowth, valClass,
        };
    },
});

app.component('institution-page', {
    template: '#institution-tpl',
    setup() {
        const ownerMeta = ref([]);
        const owner = ref('');
        const subTab = ref('overview');
        const loading = ref(false);
        const error = ref('');
        const overviewData = ref(null);
        const changeData = ref(null);
        const sectorData = ref(null);
        const stockData = ref(null);
        const crossData = ref(null);
        const quarters = ref([]);
        const changeQuarter = ref('');
        const changeAction = ref('');
        const sectorQuarter = ref('');
        const sectorType = ref('industry');
        const stockInput = ref('');

        const ownerOf = o => ownerMeta.value.find(x => x.owner_type === o);

        function ownerLabel() {
            const o = ownerOf(owner.value);
            return o ? o.label : owner.value;
        }
        function ownerLabelOf(code) {
            const o = ownerOf(code);
            return o ? o.label : code;
        }

        async function loadOwners() {
            try {
                const res = await fetch(`${API_BASE}/institution/owners`);
                const d = await res.json();
                ownerMeta.value = d.owners || [];
                quarters.value = (d.dates || []).slice().reverse().map(dateToQuarter);
                if (ownerMeta.value.length) switchOwner(ownerMeta.value[0].owner_type);
            } catch (e) { error.value = e.message; }
        }

        function dateToQuarter(d) {
            const yy = String(d).slice(2, 4);
            const q = parseInt(String(d).slice(4, 6));
            return yy + 'Q' + Math.ceil(q / 3);
        }

        function latestQuarterOf() {
            return quarters.value[0] || '';
        }

        function switchOwner(t) {
            owner.value = t;
            subTab.value = 'overview';
            stockInput.value = '';
            loadOverview();
        }

        function onSubTab(t) {
            subTab.value = t;
            if (t === 'change') loadChange();
            else if (t === 'sector') loadSector();
            else if (t === 'cross') loadCross();
        }

        async function loadOverview() {
            loading.value = true;
            error.value = '';
            try {
                const res = await fetch(`${API_BASE}/institution/${owner.value}/overview`);
                overviewData.value = await res.json();
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        async function loadChange() {
            loading.value = true;
            error.value = '';
            try {
                const q = changeQuarter.value || latestQuarterOf();
                const act = changeAction.value ? '&action=' + encodeURIComponent(changeAction.value) : '';
                const res = await fetch(`${API_BASE}/institution/${owner.value}/change?quarter=${q}${act}`);
                changeData.value = await res.json();
                if (!changeQuarter.value) changeQuarter.value = changeData.value.quarter || q;
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        async function loadSector() {
            loading.value = true;
            error.value = '';
            try {
                const q = sectorQuarter.value || latestQuarterOf();
                const res = await fetch(`${API_BASE}/institution/${owner.value}/sector?quarter=${q}&sector_type=${sectorType.value}`);
                sectorData.value = await res.json();
                if (!sectorQuarter.value) sectorQuarter.value = sectorData.value.quarter || q;
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        async function loadStock(code) {
            const c = (code || stockInput.value || '').trim();
            if (!c) return;
            loading.value = true;
            error.value = '';
            try {
                const res = await fetch(`${API_BASE}/institution/${owner.value}/stock/${c}`);
                stockData.value = await res.json();
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        function openStock(code) {
            if (!code) return;
            subTab.value = 'stock';
            stockInput.value = code;
            loadStock(code);
        }

        async function loadCross() {
            subTab.value = 'cross';
            loading.value = true;
            error.value = '';
            try {
                const q = latestQuarterOf();
                const res = await fetch(`${API_BASE}/institution/cross?types=shebao,yanglao,baoxian,caizheng,guozwei&quarter=${q}`);
                crossData.value = await res.json();
            } catch (e) { error.value = e.message; }
            loading.value = false;
        }

        function fmtPct(v) {
            if (v == null || v === '') return '-';
            return Number(v).toFixed(2) + '%';
        }
        function fmtShares(amount) {
            if (amount == null) return '-';
            return (amount / 10000).toFixed(2);
        }
        function actionColor(a) {
            return a === '增持' || a === '新开仓' ? '#22c55e' : a === '减持' || a === '清仓' ? '#ef4444' : '#8e8ea0';
        }

        onMounted(loadOwners);

        return {
            ownerMeta, owner, subTab, loading, error,
            overviewData, changeData, sectorData, stockData, crossData,
            quarters, changeQuarter, changeAction,
            sectorQuarter, sectorType, stockInput,
            ownerLabel, ownerLabelOf, switchOwner, onSubTab,
            loadOverview, loadChange, loadSector, loadStock, loadCross, openStock,
            fmtPct, fmtShares, actionColor, fmtMoney, fmtGrowth, valClass,
        };
    },
});

// ── 投资逻辑 · 事件传导网络 ──
app.component('logic-page', {
    template: '#logic-tpl',
    setup() {
        const currentPage = inject('currentPage');
        const activeEvent = ref('war');

        const events = ref([
            {
                id: 'war', icon: '⚔️', name: '地缘冲突',
                short: '俄乌/中东战争 → 能源/航运/避险',
                title: '地缘冲突（战争）全景传导',
                description: '战争是最典型的多行业共振事件：即时冲击能源与避险资产，短期传导至航运与军工，中期影响粮食与化工。核心逻辑：供需冲击 → 运距/成本重构 → 盈利与估值双升。',
                chains: [
                    {
                        name: '能源 · 石油', icon: '🛢️', timing: 1, type: 'bull',
                        desc: '战争 → 供应中断预期 → 油价暴涨（即时）',
                        nodes: [
                            { icon: '⚔️', name: '战争冲突', sub: '中东/俄乌供应受阻', type: 'trigger' },
                            { icon: '📈', name: '油价暴涨', sub: '布伦特冲高', type: 'impact' },
                            { icon: '💰', name: '油气开采盈利暴增', sub: '上游量价齐升', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '601857', name: '中国石油', logic: '上游油气开采龙头，油价弹性大', factor: ['石油', '油气开采'] },
                            { code: '600938', name: '中国海油', logic: '纯上游油气标的，成本优势突出', factor: ['海上油气', '低成本'] },
                            { code: '600028', name: '中国石化', logic: '炼化一体化，油价上行受益', factor: ['炼化', '上游'] },
                        ],
                    },
                    {
                        name: '贵金属 · 避险', icon: '🥇', timing: 1, type: 'bull',
                        desc: '战争 → 避险需求 → 金价上涨（即时）',
                        nodes: [
                            { icon: '⚔️', name: '地缘冲突', sub: '避险情绪升温', type: 'trigger' },
                            { icon: '📈', name: '金价上涨', sub: 'COMEX黄金创新高', type: 'impact' },
                            { icon: '💰', name: '黄金股量价齐升', sub: '金矿公司盈利改善', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '600547', name: '山东黄金', logic: '黄金采选龙头，金价弹性大', factor: ['黄金', '避险'] },
                            { code: '600489', name: '中金黄金', logic: '央企黄金龙头，资源储备丰富', factor: ['黄金', '央企'] },
                            { code: '601899', name: '紫金矿业', logic: '铜金双驱，全球资源龙头', factor: ['黄金', '铜'] },
                        ],
                    },
                    {
                        name: '航运 · 油运/集运', icon: '🚢', timing: 2, type: 'bull',
                        desc: '战争 → 红海封锁/制裁 → 绕行运距拉长 → 运价上涨（短期）',
                        nodes: [
                            { icon: '⚔️', name: '战争冲突', sub: '红海/海峡封锁', type: 'trigger' },
                            { icon: '🔄', name: '运距拉长', sub: '绕行好望角+10-15%', type: 'impact' },
                            { icon: '📈', name: '运价上涨', sub: 'VLCC-TCE / SCFI', type: 'impact' },
                            { icon: '💰', name: '船东盈利兑现', sub: '业绩弹性释放', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '600026', name: '中远海能', logic: '全球最大油轮船队，运价弹性最纯正', factor: ['油运', 'VLCC'] },
                            { code: '601872', name: '招商轮船', logic: 'VLCC油运龙头，油散双轮驱动', factor: ['油运', '干散货'] },
                            { code: '601919', name: '中远海控', logic: '集运龙头，红海绕行运价核心受益', factor: ['集运', '红海'] },
                        ],
                    },
                    {
                        name: '军工 · 装备', icon: '🎖️', timing: 2, type: 'bull',
                        desc: '战争 → 军费扩张预期 → 装备采购（短期）',
                        nodes: [
                            { icon: '⚔️', name: '战争冲突', sub: '军备竞赛升级', type: 'trigger' },
                            { icon: '🏛️', name: '军费扩张', sub: '国防预算上调', type: 'impact' },
                            { icon: '💰', name: '装备订单放量', sub: '主机厂/核心零部件', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '600760', name: '中航沈飞', logic: '歼击机龙头，军机放量', factor: ['军机', '主机厂'] },
                            { code: '600893', name: '航发动力', logic: '航空发动机唯一上市平台', factor: ['航发', '军工'] },
                            { code: '601989', name: '中国重工', logic: '船舶+军工装备，海军建设受益', factor: ['军工', '船舶'] },
                        ],
                    },
                    {
                        name: '粮食 · 种业', icon: '🌾', timing: 3, type: 'bull',
                        desc: '战争 → 黑海粮仓受阻 → 粮价上涨 → 种业景气（中期）',
                        nodes: [
                            { icon: '⚔️', name: '战争冲突', sub: '黑海粮食走廊受阻', type: 'trigger' },
                            { icon: '📈', name: '全球粮价上涨', sub: '小麦/玉米/油脂', type: 'impact' },
                            { icon: '💰', name: '种业量价齐升', sub: '种子涨价+推广', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '000998', name: '隆平高科', logic: '水稻/玉米种子龙头', factor: ['种业', '粮食'] },
                            { code: '600313', name: '农发种业', logic: '小麦/玉米种子，粮价弹性', factor: ['种业', '小麦'] },
                            { code: '002041', name: '登海种业', logic: '玉米种业龙头', factor: ['玉米', '种业'] },
                        ],
                    },
                    {
                        name: '化工 · 钾肥', icon: '🧪', timing: 4, type: 'bull',
                        desc: '战争 → 俄罗斯钾肥断供 → 钾肥涨价 → 农化受益（中期）',
                        nodes: [
                            { icon: '⚔️', name: '战争冲突', sub: '俄钾出口制裁', type: 'trigger' },
                            { icon: '📈', name: '钾肥价格上涨', sub: '供给收缩', type: 'impact' },
                            { icon: '💰', name: '农化盈利提升', sub: '钾肥/磷肥量价', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '000792', name: '盐湖股份', logic: '钾肥龙头，价格弹性大', factor: ['钾肥', '盐湖'] },
                            { code: '000893', name: '亚钾国际', logic: '钾肥产能扩张，量价齐升', factor: ['钾肥', '农业'] },
                        ],
                    },
                    {
                        name: '利空 · 航空', icon: '✈️', timing: 2, type: 'bear',
                        desc: '战争 → 油价暴涨 → 航油成本激增 → 航空盈利承压（短期）',
                        nodes: [
                            { icon: '⚔️', name: '战争冲突', sub: '油价暴涨', type: 'trigger' },
                            { icon: '📈', name: '航油成本飙升', sub: '燃油占总成本30%+', type: 'impact' },
                            { icon: '📉', name: '航空盈利承压', sub: '成本挤压利润', type: 'bear' },
                        ],
                        stocks: [
                            { code: '600029', name: '南方航空', logic: '航油成本敏感，油价上涨利空', factor: ['航空', '航油成本'] },
                            { code: '601111', name: '中国国航', logic: '国际航线多，油价弹性大', factor: ['航空', '航油'] },
                            { code: '600115', name: '中国东航', logic: '航油成本占比高，油价利空', factor: ['航空', '航油'] },
                        ],
                    },
                    {
                        name: '利空 · 下游制造', icon: '🏭', timing: 2, type: 'bear',
                        desc: '战争 → 油价/大宗上涨 → 原材料成本上升 → 下游毛利承压（短期）',
                        nodes: [
                            { icon: '⚔️', name: '战争冲突', sub: '大宗商品上涨', type: 'trigger' },
                            { icon: '📈', name: '原材料成本上升', sub: '塑料/化纤/运输成本', type: 'impact' },
                            { icon: '📉', name: '下游毛利承压', sub: '成本转嫁困难', type: 'bear' },
                        ],
                        stocks: [
                            { code: '600309', name: '万华化学', logic: '化工原料成本上行，短期承压', factor: ['化工', '成本'] },
                            { code: '601012', name: '隆基绿能', logic: '原材料+物流成本上升', factor: ['光伏', '成本'] },
                        ],
                    },
                    {
                        name: '利空 · 粮食进口依赖', icon: '🌾', timing: 3, type: 'bear',
                        desc: '战争 → 粮价上涨 → 饲料/养殖成本上升（中期）',
                        nodes: [
                            { icon: '⚔️', name: '战争冲突', sub: '全球粮价上涨', type: 'trigger' },
                            { icon: '📈', name: '饲料成本上升', sub: '豆粕/玉米涨价', type: 'impact' },
                            { icon: '📉', name: '养殖盈利承压', sub: '成本挤压利润', type: 'bear' },
                        ],
                        stocks: [
                            { code: '002714', name: '牧原股份', logic: '饲料成本占比高，粮价上涨利空', factor: ['养殖', '饲料成本'] },
                            { code: '000876', name: '新希望', logic: '饲料+养殖，成本敏感', factor: ['饲料', '养殖'] },
                        ],
                    },
                ],
                allStocks: [
                    { code: '601857', name: '中国石油', chain: '能源·石油', timing: 1, logic: '油价暴涨，上游开采盈利暴增' },
                    { code: '600938', name: '中国海油', chain: '能源·石油', timing: 1, logic: '纯上游油气，成本优势' },
                    { code: '600547', name: '山东黄金', chain: '贵金属·避险', timing: 1, logic: '金价上涨，避险受益' },
                    { code: '600026', name: '中远海能', chain: '航运·油运', timing: 2, logic: '油运运价弹性最纯正' },
                    { code: '601872', name: '招商轮船', chain: '航运·油运', timing: 2, logic: 'VLCC龙头，运距拉长受益' },
                    { code: '601919', name: '中远海控', chain: '航运·集运', timing: 2, logic: '红海绕行运价上涨' },
                    { code: '600760', name: '中航沈飞', chain: '军工·装备', timing: 2, logic: '军机放量' },
                    { code: '000998', name: '隆平高科', chain: '粮食·种业', timing: 3, logic: '粮价上涨，种业景气' },
                    { code: '000792', name: '盐湖股份', chain: '化工·钾肥', timing: 3, logic: '钾肥涨价' },
                ],
            },
            {
                id: 'climate', icon: '🌧️', name: '极端天气',
                short: '干旱/洪水/厄尔尼诺 → 粮食/农资/水电',
                title: '极端天气（减产）全景传导',
                description: '极端天气直接冲击农产品供给，引发粮价上涨，进而带动种业景气、农资需求提升；同时影响水电/火电出力与基建。核心逻辑：供给收缩 → 量价齐升。',
                chains: [
                    {
                        name: '粮食 · 种业', icon: '🌾', timing: 1,
                        desc: '极端天气 → 减产预期 → 粮价上涨 → 种业（即时）',
                        nodes: [
                            { icon: '🌧️', name: '极端天气', sub: '干旱/洪涝', type: 'trigger' },
                            { icon: '📉', name: '作物减产', sub: '主粮供给收缩', type: 'impact' },
                            { icon: '📈', name: '粮价上涨', sub: '期货现货上行', type: 'impact' },
                            { icon: '💰', name: '种业景气', sub: '种子涨价推广', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '000998', name: '隆平高科', logic: '水稻/玉米种子龙头', factor: ['种业', '粮食'] },
                            { code: '002041', name: '登海种业', logic: '玉米种业龙头', factor: ['玉米', '种业'] },
                            { code: '600313', name: '农发种业', logic: '小麦种子，粮价弹性', factor: ['小麦', '种业'] },
                        ],
                    },
                    {
                        name: '农化 · 化肥农药', icon: '🧪', timing: 2,
                        desc: '粮价上涨 → 农户扩种 → 化肥农药需求（短期）',
                        nodes: [
                            { icon: '📈', name: '粮价上涨', sub: '种植收益提升', type: 'trigger' },
                            { icon: '👨‍🌾', name: '扩种意愿', sub: '增加农资投入', type: 'impact' },
                            { icon: '💰', name: '农化需求回暖', sub: '化肥/农药量价', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '002556', name: '辉隆股份', logic: '农资流通龙头', factor: ['化肥', '农资'] },
                            { code: '000792', name: '盐湖股份', logic: '钾肥龙头', factor: ['钾肥', '农业'] },
                        ],
                    },
                    {
                        name: '电力 · 水电', icon: '⚡', timing: 2,
                        desc: '干旱 → 水电出力下降 → 火电/核电补位（短期）',
                        nodes: [
                            { icon: '🌧️', name: '极端干旱', sub: '来水减少', type: 'trigger' },
                            { icon: '📉', name: '水电出力下降', sub: '发电量下滑', type: 'impact' },
                            { icon: '💰', name: '火电/核电受益', sub: '发电量替代', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '600011', name: '华能国际', logic: '火电龙头，水电不足补位', factor: ['火电', '电力'] },
                            { code: '601985', name: '中国核电', logic: '核电稳定出力', factor: ['核电', '电力'] },
                        ],
                    },
                ],
                allStocks: [
                    { code: '000998', name: '隆平高科', chain: '粮食·种业', timing: 1, logic: '减产预期种业景气' },
                    { code: '002556', name: '辉隆股份', chain: '农化', timing: 2, logic: '农资需求回暖' },
                    { code: '600011', name: '华能国际', chain: '电力·火电', timing: 2, logic: '水电不足补位' },
                    { code: '601985', name: '中国核电', chain: '电力·核电', timing: 2, logic: '稳定出力' },
                ],
            },
            {
                id: 'ai', icon: '🤖', name: 'AI算力',
                short: 'AI爆发 → 半导体/服务器/光模块/电力',
                title: 'AI算力（科技革命）全景传导',
                description: 'AI大模型爆发是需求驱动的多环节共振：最上游算力需求 → 芯片/设备/材料 → 服务器/光模块 → 电力能源。核心逻辑：需求爆发 → 国产替代 → 全链景气。',
                chains: [
                    {
                        name: '半导体 · 芯片', icon: '🔌', timing: 1,
                        desc: 'AI需求 → GPU/CPU/ASIC 订单爆发（即时）',
                        nodes: [
                            { icon: '🤖', name: 'AI大模型', sub: '算力需求指数增长', type: 'trigger' },
                            { icon: '📈', name: 'AI芯片需求', sub: 'GPU/HBM/ASIC', type: 'impact' },
                            { icon: '💰', name: '芯片设计盈利', sub: 'ASP提升订单饱满', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '688256', name: '寒武纪', logic: 'AI芯片龙头，弹性最大', factor: ['AI芯片', 'GPU'] },
                            { code: '688041', name: '海光信息', logic: '国产CPU/DCU，算力受益', factor: ['CPU', 'DCU'] },
                            { code: '603501', name: '韦尔股份', logic: 'CIS设计龙头', factor: ['CIS', '芯片'] },
                        ],
                    },
                    {
                        name: '半导体 · 设备材料', icon: '🔧', timing: 2,
                        desc: '晶圆厂扩产 → 国产设备/材料放量（短期）',
                        nodes: [
                            { icon: '🏭', name: '晶圆厂扩产', sub: '产能满载+新建', type: 'trigger' },
                            { icon: '📈', name: '设备订单', sub: '刻蚀/薄膜/光刻', type: 'impact' },
                            { icon: '💰', name: '设备材料盈利', sub: '国产替代加速', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '002371', name: '北方华创', logic: '设备平台龙头', factor: ['设备', '国产替代'] },
                            { code: '688012', name: '中微公司', logic: '刻蚀设备龙头', factor: ['刻蚀', '设备'] },
                            { code: '688126', name: '沪硅产业', logic: '大硅片材料', factor: ['硅片', '材料'] },
                        ],
                    },
                    {
                        name: '算力基建 · 服务器/光模块', icon: '🖥️', timing: 3,
                        desc: '数据中心建设 → 服务器/光模块/交换机（中期）',
                        nodes: [
                            { icon: '🏗️', name: '数据中心建设', sub: '智算中心放量', type: 'trigger' },
                            { icon: '📈', name: '算力硬件需求', sub: '服务器/光模块', type: 'impact' },
                            { icon: '💰', name: '硬件厂商受益', sub: '订单+涨价', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '601138', name: '工业富联', logic: 'AI服务器代工龙头', factor: ['AI服务器', '算力'] },
                            { code: '300308', name: '中际旭创', logic: '光模块龙头，800G放量', factor: ['光模块', '800G'] },
                            { code: '000977', name: '浪潮信息', logic: '国产服务器龙头', factor: ['服务器', '算力'] },
                        ],
                    },
                    {
                        name: '电力 · 能源', icon: '⚡', timing: 4,
                        desc: '算力耗电 → 核电/绿电需求（长期）',
                        nodes: [
                            { icon: '🤖', name: 'AI耗电', sub: '数据中心用电激增', type: 'trigger' },
                            { icon: '📈', name: '电力需求', sub: '绿电/核电/火电', type: 'impact' },
                            { icon: '💰', name: '电力运营商受益', sub: '电量电价双升', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '601985', name: '中国核电', logic: '核电稳定增长', factor: ['核电', '电力'] },
                            { code: '600900', name: '长江电力', logic: '水电龙头，稳定现金流', factor: ['水电', '电力'] },
                        ],
                    },
                ],
                allStocks: [
                    { code: '688256', name: '寒武纪', chain: '半导体·芯片', timing: 1, logic: 'AI芯片弹性最大' },
                    { code: '688041', name: '海光信息', chain: '半导体·芯片', timing: 1, logic: '国产CPU/DCU' },
                    { code: '002371', name: '北方华创', chain: '半导体·设备', timing: 2, logic: '设备平台龙头' },
                    { code: '601138', name: '工业富联', chain: '算力基建', timing: 3, logic: 'AI服务器龙头' },
                    { code: '300308', name: '中际旭创', chain: '算力基建', timing: 3, logic: '光模块800G放量' },
                    { code: '601985', name: '中国核电', chain: '电力·能源', timing: 4, logic: '算力耗电受益' },
                    { code: '600900', name: '长江电力', chain: '电力·能源', timing: 4, logic: '稳定电力龙头' },
                ],
            },
            {
                id: 'aigc', icon: '✨', name: 'AIGC应用',
                short: '生成式AI → 算力/应用/数据安全',
                title: 'AIGC（生成式AI）全景传导',
                description: 'AIGC是本轮AI产业的核心爆发点：底层是算力需求爆发，中间是模型/平台能力提升，顶层是各类应用落地与商业化。核心逻辑：算力先行 → 应用变现 → 数据与安全受益。',
                chains: [
                    {
                        name: '算力硬件 · 芯片/服务器', icon: '🔌', timing: 1,
                        desc: 'AIGC模型训练/推理 → 算力需求爆发（即时）',
                        nodes: [
                            { icon: '✨', name: 'AIGC爆发', sub: '大模型训练/推理', type: 'trigger' },
                            { icon: '📈', name: '算力需求', sub: 'GPU/CPU/服务器', type: 'impact' },
                            { icon: '💰', name: '算力硬件盈利', sub: '订单饱满+涨价', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '688256', name: '寒武纪', logic: 'AI芯片龙头，训练推理需求', factor: ['AI芯片', 'GPU'] },
                            { code: '688041', name: '海光信息', logic: '国产DCU/CPU，算力核心', factor: ['DCU', '国产算力'] },
                            { code: '601138', name: '工业富联', logic: 'AI服务器代工龙头', factor: ['AI服务器', '算力'] },
                        ],
                    },
                    {
                        name: '算力基建 · 光模块/液冷', icon: '🖥️', timing: 2,
                        desc: '算力集群建设 → 网络/散热配套（短期）',
                        nodes: [
                            { icon: '🏗️', name: '算力集群建设', sub: '智算中心/大集群', type: 'trigger' },
                            { icon: '📡', name: '网络/散热需求', sub: '光模块/液冷/PCB', type: 'impact' },
                            { icon: '💰', name: '配套硬件受益', sub: '量价齐升', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '300308', name: '中际旭创', logic: '光模块龙头，AI网络核心', factor: ['光模块', '800G'] },
                            { code: '002463', name: '沪电股份', logic: '高多层PCB，AI服务器用', factor: ['PCB', 'AI服务器'] },
                            { code: '000977', name: '浪潮信息', logic: '国产服务器，智算中心', factor: ['服务器', '智算'] },
                        ],
                    },
                    {
                        name: 'AI应用 · 办公/传媒/电商', icon: '💼', timing: 3,
                        desc: '模型能力 → 应用商业化落地（中期）',
                        nodes: [
                            { icon: '📦', name: '模型平台化', sub: 'API/工具成熟', type: 'trigger' },
                            { icon: '💼', name: '应用落地', sub: '办公/传媒/教育/电商', type: 'impact' },
                            { icon: '💰', name: '应用变现', sub: '订阅/广告/提效', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '688111', name: '金山办公', logic: 'WPS AI，办公提效', factor: ['AI办公', 'WPS'] },
                            { code: '002230', name: '科大讯飞', logic: 'AI应用龙头，星火大模型', factor: ['大模型', 'AI应用'] },
                            { code: '300413', name: '芒果超媒', logic: 'AI内容生成，传媒降本', factor: ['AI传媒', '内容'] },
                        ],
                    },
                    {
                        name: '数据 · 安全/数据要素', icon: '🔐', timing: 4,
                        desc: 'AI依赖数据 → 数据要素/安全（长期）',
                        nodes: [
                            { icon: '📊', name: 'AI数据需求', sub: '高质量训练数据', type: 'trigger' },
                            { icon: '🔐', name: '数据安全/要素', sub: '合规/确权/交易', type: 'impact' },
                            { icon: '💰', name: '数据服务受益', sub: '数据要素产业化', type: 'benefit' },
                        ],
                        stocks: [
                            { code: '688561', name: '奇安信', logic: '网络安全龙头，AI安全', factor: ['网络安全', 'AI安全'] },
                            { code: '300229', name: '拓尔思', logic: '数据要素+语义智能', factor: ['数据要素', '语义AI'] },
                        ],
                    },
                ],
                allStocks: [
                    { code: '688256', name: '寒武纪', chain: '算力硬件·芯片', timing: 1, logic: 'AI芯片需求爆发' },
                    { code: '688041', name: '海光信息', chain: '算力硬件·芯片', timing: 1, logic: '国产DCU/CPU' },
                    { code: '601138', name: '工业富联', chain: '算力硬件·服务器', timing: 1, logic: 'AI服务器龙头' },
                    { code: '300308', name: '中际旭创', chain: '算力基建·光模块', timing: 2, logic: '光模块800G放量' },
                    { code: '002463', name: '沪电股份', chain: '算力基建·PCB', timing: 2, logic: 'AI服务器PCB' },
                    { code: '688111', name: '金山办公', chain: 'AI应用·办公', timing: 3, logic: 'WPS AI提效' },
                    { code: '002230', name: '科大讯飞', chain: 'AI应用', timing: 3, logic: '星火大模型' },
                    { code: '688561', name: '奇安信', chain: '数据·安全', timing: 4, logic: 'AI安全龙头' },
                ],
            },
        ]);

        const ev = computed(() => events.value.find(e => e.id === activeEvent.value));

        function switchEvent(id) { activeEvent.value = id; }

        function timingLabel(t) {
            const names = { 1: '即时', 2: '短期', 3: '中期', 4: '长期' };
            return names[t] || '';
        }

        function goStock(code) {
            window._profileStockCode = code;
            currentPage.value = 'profile';
        }

        const viewMode = ref('event');
        const activeSector = ref('880301');

        const sectorGroups = ref([
            {
                id: 'cycle', name: '周期资源', icon: '⛰️',
                industries: [
                    {
                        code: '880301', name: '煤炭', icon: '⛏️',
                        desc: '黑色能源，动力煤+焦煤双主线',
                        logic: '煤价由供需决定：动力煤看电厂日耗+库存，焦煤看钢厂高炉开工。政策保供稳价是最大变量，高分红+低估值提供安全边际。',
                        drivers: [
                            { icon: '🌡️', name: '迎峰度夏/度冬', desc: '用电旺季电厂日耗上升→动力煤价上行' },
                            { icon: '🏗️', name: '焦煤需求', desc: '钢厂高炉开工率→焦煤需求' },
                            { icon: '📜', name: '长协+保供政策', desc: '长协价稳定利润，政策压制煤价上限' },
                        ],
                        upstream: [{ icon: '🏭', name: '煤机设备', desc: '煤炭开采机械需求' }],
                        downstream: [{ icon: '⚡', name: '火电', desc: '动力煤下游，发电耗煤' }, { icon: '🏗️', name: '焦化/钢铁', desc: '焦煤下游炼焦' }],
                        stocks: [
                            { code: '601088', name: '中国神华', logic: '煤电一体化，高分红龙头' },
                            { code: '600188', name: '兖矿能源', logic: '动力煤+化工，业绩弹性' },
                            { code: '601898', name: '中煤能源', logic: '央企煤炭，煤电一体化' },
                        ],
                    },
                    {
                        code: '880310', name: '石油', icon: '🛢️',
                        desc: '油气开采+炼化双主线，油价是核心变量',
                        logic: '油价由OPEC+供给+地缘+全球需求决定。上游开采盈利随油价弹性放大，炼化受油价波动影响。高油价利好上游，低油价利好炼化成本。',
                        drivers: [
                            { icon: '⚔️', name: '地缘冲突', desc: '中东/俄乌→供应中断预期→油价暴涨' },
                            { icon: '🛢️', name: 'OPEC+减产', desc: '供给端调控→油价中枢上移' },
                            { icon: '🌍', name: '全球需求', desc: '经济复苏→原油需求增长' },
                        ],
                        upstream: [{ icon: '⛏️', name: '油服设备', desc: '油气开采装备需求' }],
                        downstream: [{ icon: '🧪', name: '炼化', desc: '原油炼制成成品油/化工' }, { icon: '🚗', name: '成品油消费', desc: '交通用油需求' }],
                        stocks: [
                            { code: '601857', name: '中国石油', logic: '上游油气龙头，油价弹性' },
                            { code: '600938', name: '中国海油', logic: '纯上游，成本优势突出' },
                            { code: '600028', name: '中国石化', logic: '炼化一体化，综合受益' },
                        ],
                    },
                    {
                        code: '880318', name: '钢铁', icon: '🔩',
                        desc: '普钢+特钢，地产基建需求主导',
                        logic: '钢铁受地产/基建/制造业需求驱动，供给端受粗钢压减+铁矿成本影响。地产企稳+基建发力→需求改善，高端特钢成长性强。',
                        drivers: [
                            { icon: '🏗️', name: '地产/基建', desc: '地产开工+基建投资→钢材需求' },
                            { icon: '📉', name: '粗钢压减', desc: '限产政策→供给收缩→钢价支撑' },
                            { icon: '⛏️', name: '铁矿成本', desc: '铁矿石价格→钢企成本' },
                        ],
                        upstream: [{ icon: '⛏️', name: '铁矿石', desc: '炼钢原料' }, { icon: '⚫', name: '焦炭', desc: '炼焦煤加工' }],
                        downstream: [{ icon: '🏗️', name: '房地产', desc: '螺纹钢需求' }, { icon: '🚗', name: '汽车/机械', desc: '板材/特钢需求' }],
                        stocks: [
                            { code: '600019', name: '宝钢股份', logic: '普钢龙头，汽车板优势' },
                            { code: '000708', name: '中信特钢', logic: '特钢龙头，高端制造' },
                        ],
                    },
                    {
                        code: '880324', name: '有色', icon: '🥇',
                        desc: '铜铝铅锌黄金，工业金属+贵金属',
                        logic: '铜铝看全球需求+新能源拉动，黄金看避险+美元+降息。新能源（电动车/光伏）提升铜铝需求，宏观宽松利好贵金属。',
                        drivers: [
                            { icon: '🚗', name: '新能源需求', desc: '电动车/光伏/电网→铜铝需求' },
                            { icon: '💵', name: '美元/降息', desc: '美元走弱+降息→黄金上涨' },
                            { icon: '🌍', name: '全球补库', desc: '经济复苏→工业金属需求' },
                        ],
                        upstream: [{ icon: '⛏️', name: '矿山', desc: '铜矿/铝土矿' }],
                        downstream: [{ icon: '🚗', name: '新能源车', desc: '铜铝需求' }, { icon: '⚡', name: '电网/光伏', desc: '有色金属需求' }],
                        stocks: [
                            { code: '601899', name: '紫金矿业', logic: '铜金龙头，全球资源' },
                            { code: '601600', name: '中国铝业', logic: '电解铝龙头，新能源受益' },
                            { code: '600547', name: '山东黄金', logic: '黄金龙头，避险弹性' },
                        ],
                    },
                    {
                        code: '880330', name: '化纤', icon: '🧵',
                        desc: '涤纶/粘胶，纺织原料',
                        logic: '化纤受油价（原料PX/PTA）+下游纺织需求驱动。产能周期决定景气，油价上行+需求回暖→价差扩大。',
                        drivers: [
                            { icon: '🛢️', name: '油价', desc: 'PTA/PX原料成本' },
                            { icon: '👕', name: '纺织需求', desc: '下游服装出口' },
                            { icon: '🏭', name: '产能周期', desc: '新增产能→价差' },
                        ],
                        upstream: [{ icon: '🛢️', name: '原油/PTA', desc: '化纤原料' }],
                        downstream: [{ icon: '👕', name: '纺织服装', desc: '涤纶/粘胶需求' }],
                        stocks: [
                            { code: '600346', name: '恒力石化', logic: '炼化+化纤一体化' },
                            { code: '000301', name: '东方盛虹', logic: '炼化+涤纶龙头' },
                        ],
                    },
                    {
                        code: '880335', name: '化工', icon: '🧪',
                        desc: '基础化工，周期+成长',
                        logic: '化工品价格由供需决定，油价是成本端变量。地产/纺服/农业需求驱动，供给端受产能周期影响。细分看新材料/农药/化纤成长。',
                        drivers: [
                            { icon: '🛢️', name: '油价成本', desc: '化工品原料成本' },
                            { icon: '🏗️', name: '地产/纺服需求', desc: '下游消费需求' },
                            { icon: '🏭', name: '产能周期', desc: '供给端扩张/收缩' },
                        ],
                        upstream: [{ icon: '🛢️', name: '原油/煤炭', desc: '化工原料' }],
                        downstream: [{ icon: '🌾', name: '农业', desc: '化肥需求' }, { icon: '🚗', name: '汽车/电子', desc: '新材料需求' }],
                        stocks: [
                            { code: '600309', name: '万华化学', logic: 'MDI龙头，化工白马' },
                            { code: '002648', name: '卫星化学', logic: '轻烃化工，成长性强' },
                        ],
                    },
                    {
                        code: '880344', name: '建材', icon: '🏗️',
                        desc: '水泥+玻璃+消费建材',
                        logic: '建材受地产/基建需求驱动，水泥看区域供给格局+错峰生产，玻璃看地产竣工，消费建材看地产后周期。',
                        drivers: [
                            { icon: '🏗️', name: '地产/基建', desc: '水泥/玻璃需求' },
                            { icon: '🏭', name: '错峰生产', desc: '供给约束→水泥价格' },
                            { icon: '🏠', name: '地产竣工', desc: '玻璃/消费建材需求' },
                        ],
                        upstream: [{ icon: '⛏️', name: '石灰石/纯碱', desc: '建材原料' }],
                        downstream: [{ icon: '🏗️', name: '房地产/基建', desc: '水泥需求' }, { icon: '🏠', name: '家装', desc: '消费建材需求' }],
                        stocks: [
                            { code: '600585', name: '海螺水泥', logic: '水泥龙头，成本优势' },
                            { code: '601636', name: '旗滨集团', logic: '玻璃龙头，光伏玻璃' },
                        ],
                    },
                    {
                        code: '880350', name: '造纸', icon: '📄',
                        desc: '纸浆+成品纸，周期消费',
                        logic: '造纸受纸浆成本+下游需求（包装/文化纸）驱动。浆价是核心变量，需求看消费/出口。',
                        drivers: [
                            { icon: '🌲', name: '纸浆价格', desc: '木浆成本' },
                            { icon: '📦', name: '包装需求', desc: '快递/消费包装' },
                            { icon: '🌍', name: '出口', desc: '成品纸出口' },
                        ],
                        upstream: [{ icon: '🌲', name: '木浆', desc: '造纸原料' }],
                        downstream: [{ icon: '📦', name: '包装', desc: '瓦楞/白卡需求' }, { icon: '📚', name: '文化纸', desc: '教材/办公' }],
                        stocks: [
                            { code: '600966', name: '博汇纸业', logic: '白卡纸龙头' },
                            { code: '600308', name: '华泰股份', logic: '新闻纸/文化纸' },
                        ],
                    },
                ],
            },
            {
                id: 'consumer', name: '大消费', icon: '🛍️',
                industries: [
                    {
                        code: '880360', name: '农林牧渔', icon: '🌾',
                        desc: '种植+养殖，粮食安全',
                        logic: '受农产品价格驱动，猪周期看产能去化，种业看粮食安全+转基因，养殖看猪价/鸡价。粮价上涨利好种业种植。',
                        drivers: [
                            { icon: '🐷', name: '猪周期', desc: '母猪产能→猪价' },
                            { icon: '🌾', name: '粮食安全', desc: '粮价+转基因商业化' },
                            { icon: '🐔', name: '禽养殖', desc: '鸡价周期' },
                        ],
                        upstream: [{ icon: '🌱', name: '种子/饲料', desc: '养殖种植投入品' }],
                        downstream: [{ icon: '🍖', name: '肉制品', desc: '猪肉/鸡肉消费' }],
                        stocks: [
                            { code: '002714', name: '牧原股份', logic: '生猪养殖龙头' },
                            { code: '000998', name: '隆平高科', logic: '种业龙头' },
                            { code: '000876', name: '新希望', logic: '饲料+养殖一体化' },
                        ],
                    },
                    {
                        code: '880372', name: '食品饮料', icon: '🍜',
                        desc: '调味品+乳品+零食，消费刚需',
                        logic: '必选消费，需求稳定。受消费复苏+成本（大豆/糖）+提价能力驱动。龙头品牌力强，提价转嫁成本。',
                        drivers: [
                            { icon: '📈', name: '消费复苏', desc: '居民消费意愿' },
                            { icon: '🧂', name: '提价能力', desc: '调味品/零食提价' },
                            { icon: '🌱', name: '原料成本', desc: '大豆/糖等成本' },
                        ],
                        upstream: [{ icon: '🌾', name: '农产品原料', desc: '大豆/小麦/糖' }],
                        downstream: [{ icon: '🛒', name: '商超/电商', desc: '终端零售' }],
                        stocks: [
                            { code: '600887', name: '伊利股份', logic: '乳制品龙头' },
                            { code: '603288', name: '海天味业', logic: '调味品龙头' },
                        ],
                    },
                    {
                        code: '880380', name: '酿酒', icon: '🍶',
                        desc: '白酒+啤酒+红酒',
                        logic: '白酒看高端需求+库存周期，啤酒看高端化+提价，红酒偏小众。白酒是消费升级核心，茅台等高端酒提价能力强。',
                        drivers: [
                            { icon: '🍶', name: '白酒需求', desc: '高端白酒景气' },
                            { icon: '🏭', name: '库存周期', desc: '渠道库存去化' },
                            { icon: '🍺', name: '啤酒高端化', desc: '吨价提升' },
                        ],
                        upstream: [{ icon: '🌾', name: '粮食/麦芽', desc: '酿酒原料' }],
                        downstream: [{ icon: '🍽️', name: '餐饮/宴请', desc: '白酒消费场景' }],
                        stocks: [
                            { code: '600519', name: '贵州茅台', logic: '白酒龙头，提价能力' },
                            { code: '000858', name: '五粮液', logic: '高端白酒' },
                            { code: '600809', name: '山西汾酒', logic: '次高端成长' },
                        ],
                    },
                    {
                        code: '880387', name: '家用电器', icon: '📺',
                        desc: '白电+黑电+小家电',
                        logic: '家电看地产竣工+以旧换新+出口。白电格局好盈利稳，黑电受面板周期，小家电看新品。出口+政策补贴驱动。',
                        drivers: [
                            { icon: '🏠', name: '地产竣工', desc: '家电购置需求' },
                            { icon: '🔄', name: '以旧换新', desc: '政策补贴拉动' },
                            { icon: '🌍', name: '出口', desc: '海外需求' },
                        ],
                        upstream: [{ icon: '🔩', name: '铜铝/压缩机', desc: '家电核心部件' }],
                        downstream: [{ icon: '🏠', name: '终端消费', desc: '家庭购买' }],
                        stocks: [
                            { code: '000333', name: '美的集团', logic: '白电龙头' },
                            { code: '000651', name: '格力电器', logic: '空调龙头' },
                            { code: '600690', name: '海尔智家', logic: '白电全球化' },
                        ],
                    },
                    {
                        code: '880355', name: '日用化工', icon: '🧴',
                        desc: '日化用品，消费刚需',
                        logic: '日化受消费需求+成本（油脂/包装）+渠道变革驱动。龙头品牌力强，个人护理/清洁用品需求稳定。',
                        drivers: [
                            { icon: '🛒', name: '消费需求', desc: '日化刚需' },
                            { icon: '🌴', name: '油脂成本', desc: '原料棕榈油等' },
                            { icon: '🛍️', name: '渠道', desc: '电商/新零售' },
                        ],
                        upstream: [{ icon: '🌴', name: '油脂/表面活性剂', desc: '日化原料' }],
                        downstream: [{ icon: '🛒', name: '商超/电商', desc: '终端零售' }],
                        stocks: [
                            { code: '600315', name: '上海家化', logic: '日化龙头' },
                            { code: '603605', name: '珀莱雅', logic: '美妆成长' },
                        ],
                    },
                    {
                        code: '880367', name: '纺织服饰', icon: '👕',
                        desc: '纺织+服装+家纺',
                        logic: '纺织看出口+棉价，服装看消费+品牌升级，家纺看地产。出口链+品牌消费双主线。',
                        drivers: [
                            { icon: '🌍', name: '出口', desc: '纺织出口订单' },
                            { icon: '🌱', name: '棉价', desc: '棉花成本' },
                            { icon: '🛍️', name: '品牌消费', desc: '国潮/运动服饰' },
                        ],
                        upstream: [{ icon: '🌾', name: '棉花/化纤', desc: '纺织原料' }],
                        downstream: [{ icon: '🛍️', name: '服装零售', desc: '品牌消费' }],
                        stocks: [
                            { code: '002563', name: '森马服饰', logic: '大众服饰' },
                            { code: '600398', name: '海澜之家', logic: '男装龙头' },
                        ],
                    },
                    {
                        code: '880406', name: '商业连锁', icon: '🏬',
                        desc: '零售/超市/百货',
                        logic: '零售受消费景气+新零售变革驱动。超市看生鲜供应链，百货看可选消费，免税/会员店新业态成长。',
                        drivers: [
                            { icon: '🛒', name: '消费景气', desc: '零售额增长' },
                            { icon: '🛍️', name: '新零售', desc: '会员店/折扣业态' },
                            { icon: '💳', name: '免税', desc: '免税消费' },
                        ],
                        upstream: [{ icon: '🏭', name: '品牌商', desc: '商品采购' }],
                        downstream: [{ icon: '👤', name: '消费者', desc: '终端零售' }],
                        stocks: [
                            { code: '002024', name: 'ST易购', logic: '家电零售' },
                            { code: '601933', name: '永辉超市', logic: '生鲜超市' },
                        ],
                    },
                    {
                        code: '880423', name: '酒店餐饮', icon: '🍽️',
                        desc: '酒店+餐饮，出行消费',
                        logic: '受出行/旅游景气+消费复苏驱动。酒店看入住率+RevPAR，餐饮看翻台率+开店扩张。',
                        drivers: [
                            { icon: '✈️', name: '出行恢复', desc: '旅游/商旅需求' },
                            { icon: '🏨', name: '酒店RevPAR', desc: '入住率+房价' },
                            { icon: '🍽️', name: '餐饮扩张', desc: '开店+翻台' },
                        ],
                        upstream: [{ icon: '🏢', name: '物业/食材', desc: '酒店餐饮成本' }],
                        downstream: [{ icon: '👤', name: '消费者', desc: '住宿餐饮消费' }],
                        stocks: [
                            { code: '600754', name: '锦江酒店', logic: '酒店龙头' },
                            { code: '601007', name: '金陵饭店', logic: '酒店餐饮' },
                        ],
                    },
                ],
            },
            {
                id: 'pharma', name: '医药', icon: '💊',
                industries: [
                    {
                        code: '880398', name: '医疗保健', icon: '🏥',
                        desc: '医疗服务+器械+中药',
                        logic: '医药受政策（集采）+创新+消费医疗驱动。创新药/械政策支持，中药传承，医疗服务看老龄化。集采压制仿制药，创新是主线。',
                        drivers: [
                            { icon: '🧬', name: '创新药', desc: '研发管线+出海' },
                            { icon: '📜', name: '集采政策', desc: '仿制药降价' },
                            { icon: '👴', name: '老龄化', desc: '医疗需求增长' },
                        ],
                        upstream: [{ icon: '🧪', name: '原料药/CXO', desc: '医药研发生产外包' }],
                        downstream: [{ icon: '🏥', name: '医院/药店', desc: '终端用药' }],
                        stocks: [
                            { code: '600276', name: '恒瑞医药', logic: '创新药龙头' },
                            { code: '300760', name: '迈瑞医疗', logic: '医疗器械龙头' },
                            { code: '600085', name: '同仁堂', logic: '中药龙头' },
                        ],
                    },
                ],
            },
            {
                id: 'tech', name: '科技成长', icon: '💻',
                industries: [
                    {
                        code: '880491', name: '半导体', icon: '🔌',
                        desc: '芯片设计+制造+设备材料',
                        logic: 'AI算力+国产替代双主线。设计看AI芯片/SoC，制造看晶圆代工扩产，设备材料看国产化率提升。出口管制倒逼自主可控。',
                        drivers: [
                            { icon: '🤖', name: 'AI算力', desc: 'GPU/HBM需求爆发' },
                            { icon: '🇨🇳', name: '国产替代', desc: '设备/材料导入' },
                            { icon: '🏭', name: '晶圆扩产', desc: '产能满载' },
                        ],
                        upstream: [{ icon: '🔧', name: '设备材料', desc: '光刻/刻蚀/硅片' }],
                        downstream: [{ icon: '📱', name: '消费电子/汽车', desc: '芯片应用' }, { icon: '🤖', name: 'AI算力', desc: '数据中心' }],
                        stocks: [
                            { code: '688981', name: '中芯国际', logic: '代工龙头' },
                            { code: '688256', name: '寒武纪', logic: 'AI芯片' },
                            { code: '002371', name: '北方华创', logic: '设备龙头' },
                        ],
                    },
                    {
                        code: '880492', name: '元器件', icon: '🔩',
                        desc: '被动元件+PCB+连接器',
                        logic: '受下游需求（消费电子/汽车/服务器）驱动。AI服务器+新能源车提升PCB/MLCC需求，国产替代加速。',
                        drivers: [
                            { icon: '🤖', name: 'AI服务器', desc: '高多层PCB需求' },
                            { icon: '🚗', name: '新能源车', desc: '电子元器件用量' },
                            { icon: '🇨🇳', name: '国产替代', desc: 'MLCC/连接器' },
                        ],
                        upstream: [{ icon: '🥉', name: '铜箔/覆铜板', desc: 'PCB原料' }],
                        downstream: [{ icon: '📱', name: '消费电子', desc: '元器件应用' }, { icon: '🤖', name: '服务器', desc: 'PCB需求' }],
                        stocks: [
                            { code: '002463', name: '沪电股份', logic: '高多层PCB龙头' },
                            { code: '002938', name: '鹏鼎控股', logic: 'PCB龙头' },
                        ],
                    },
                    {
                        code: '880490', name: '通信设备', icon: '📡',
                        desc: '5G+光模块+主设备',
                        logic: '受5G建设+AI数据中心+运营商资本开支驱动。光模块受AI算力拉动，主设备看运营商招标，物联网成长。',
                        drivers: [
                            { icon: '🤖', name: 'AI光模块', desc: '800G/1.6T需求' },
                            { icon: '📡', name: '5G建设', desc: '主设备招标' },
                            { icon: '🌍', name: '运营商资本开支', desc: '通信投资' },
                        ],
                        upstream: [{ icon: '💎', name: '光芯片/光纤', desc: '光模块核心' }],
                        downstream: [{ icon: '🤖', name: '数据中心', desc: '光模块需求' }, { icon: '📱', name: '运营商', desc: '主设备采购' }],
                        stocks: [
                            { code: '300308', name: '中际旭创', logic: '光模块龙头' },
                            { code: '000063', name: '中兴通讯', logic: '主设备龙头' },
                        ],
                    },
                    {
                        code: '880489', name: 'IT设备', icon: '🖥️',
                        desc: '服务器+PC+存储',
                        logic: '受AI算力+信创+企业IT支出驱动。AI服务器需求爆发，信创国产化，存储看价格周期。',
                        drivers: [
                            { icon: '🤖', name: 'AI服务器', desc: '算力需求' },
                            { icon: '🇨🇳', name: '信创', desc: '国产化替代' },
                            { icon: '💾', name: '存储周期', desc: 'DRAM/NAND价格' },
                        ],
                        upstream: [{ icon: '🔌', name: 'CPU/GPU/存储', desc: 'IT设备核心' }],
                        downstream: [{ icon: '🤖', name: '数据中心', desc: '服务器需求' }, { icon: '🏢', name: '政企', desc: '信创采购' }],
                        stocks: [
                            { code: '601138', name: '工业富联', logic: 'AI服务器龙头' },
                            { code: '000977', name: '浪潮信息', logic: '服务器龙头' },
                        ],
                    },
                    {
                        code: '880493', name: '软件服务', icon: '💻',
                        desc: '行业软件+云+SaaS',
                        logic: '受数字化转型+AI+信创驱动。AI应用落地，国产软件替代，云服务增长。政策支持数字经济。',
                        drivers: [
                            { icon: '🤖', name: 'AI应用', desc: '大模型+软件' },
                            { icon: '🇨🇳', name: '信创', desc: '国产软件' },
                            { icon: '☁️', name: '云化', desc: 'SaaS转型' },
                        ],
                        upstream: [{ icon: '🖥️', name: '硬件/云基础设施', desc: '软件运行平台' }],
                        downstream: [{ icon: '🏢', name: '政企客户', desc: '行业软件需求' }],
                        stocks: [
                            { code: '600588', name: '用友网络', logic: 'ERP龙头' },
                            { code: '688111', name: '金山办公', logic: '办公软件' },
                        ],
                    },
                    {
                        code: '880494', name: '互联网', icon: '🌐',
                        desc: '平台经济+电商+游戏',
                        logic: '受流量+商业化+监管政策驱动。电商/游戏/广告变现，AI赋能，政策监管趋缓利好平台。',
                        drivers: [
                            { icon: '📱', name: '流量', desc: '用户时长' },
                            { icon: '🤖', name: 'AI赋能', desc: '降本增效' },
                            { icon: '📜', name: '政策监管', desc: '平台经济支持' },
                        ],
                        upstream: [{ icon: '💻', name: '软件/云', desc: '互联网基础设施' }],
                        downstream: [{ icon: '👤', name: '用户', desc: 'C端消费' }],
                        stocks: [
                            { code: '002230', name: '科大讯飞', logic: 'AI应用龙头' },
                        ],
                    },
                    {
                        code: '880418', name: '传媒娱乐', icon: '🎬',
                        desc: '影视+游戏+广告',
                        logic: '受内容供给+流量+消费复苏驱动。游戏版号常态化，影视复苏，广告随经济回暖。AI+传媒降本增效。',
                        drivers: [
                            { icon: '🎮', name: '游戏版号', desc: '供给恢复' },
                            { icon: '🎬', name: '影视复苏', desc: '票房/剧集' },
                            { icon: '🤖', name: 'AI内容', desc: '降本增效' },
                        ],
                        upstream: [{ icon: '🎭', name: '内容制作', desc: '影视/游戏研发' }],
                        downstream: [{ icon: '👤', name: '用户', desc: '娱乐消费' }],
                        stocks: [
                            { code: '002555', name: '三七互娱', logic: '游戏龙头' },
                            { code: '300413', name: '芒果超媒', logic: '内容平台' },
                        ],
                    },
                ],
            },
            {
                id: 'manufacture', name: '中游制造', icon: '⚙️',
                industries: [
                    {
                        code: '880390', name: '汽车类', icon: '🚗',
                        desc: '整车+零部件，新能源转型',
                        logic: '汽车电动化+智能化转型主线。新能源车渗透率提升，出口增长，智能驾驶升级。产业链看电池/零部件国产化。',
                        drivers: [
                            { icon: '🔋', name: '新能源车', desc: '渗透率提升' },
                            { icon: '🌍', name: '出口', desc: '整车出海' },
                            { icon: '🤖', name: '智能化', desc: '智驾+座舱' },
                        ],
                        upstream: [{ icon: '🔋', name: '电池/锂电', desc: '整车核心' }, { icon: '🔩', name: '零部件', desc: '汽车配件' }],
                        downstream: [{ icon: '👤', name: '消费者', desc: '购车需求' }],
                        stocks: [
                            { code: '002594', name: '比亚迪', logic: '新能源车龙头' },
                            { code: '601633', name: '长城汽车', logic: 'SUV+新能源' },
                            { code: '300750', name: '宁德时代', logic: '动力电池龙头' },
                        ],
                    },
                    {
                        code: '880437', name: '通用机械', icon: '🔧',
                        desc: '机床/工业机械/机械基件',
                        logic: '受制造业投资+设备更新+出口驱动。机床看工业母机国产化，工程机械看基建/地产，通用机械看制造业资本开支。',
                        drivers: [
                            { icon: '🏭', name: '制造业投资', desc: '资本开支' },
                            { icon: '🇨🇳', name: '工业母机', desc: '机床国产化' },
                            { icon: '🌍', name: '出口', desc: '机械出口' },
                        ],
                        upstream: [{ icon: '🔩', name: '钢材/轴承', desc: '机械核心件' }],
                        downstream: [{ icon: '🏭', name: '制造业', desc: '机床/机械需求' }],
                        stocks: [
                            { code: '600031', name: '三一重工', logic: '工程机械龙头' },
                            { code: '300124', name: '汇川技术', logic: '工控龙头' },
                        ],
                    },
                    {
                        code: '880446', name: '电气设备', icon: '⚡',
                        desc: '电力设备+新能源+电网',
                        logic: '受电网投资+新能源装机+出口驱动。特高压/电网设备受益电网投资，光伏/风电装机增长，储能爆发。',
                        drivers: [
                            { icon: '🌞', name: '新能源装机', desc: '光伏/风电' },
                            { icon: '⚡', name: '电网投资', desc: '特高压/配网' },
                            { icon: '🔋', name: '储能', desc: '需求爆发' },
                        ],
                        upstream: [{ icon: '🔩', name: '铜/硅料', desc: '电力设备原料' }],
                        downstream: [{ icon: '🏭', name: '电网/新能源电站', desc: '设备需求' }],
                        stocks: [
                            { code: '601012', name: '隆基绿能', logic: '光伏龙头' },
                            { code: '300274', name: '阳光电源', logic: '逆变器+储能' },
                            { code: '600406', name: '国电南瑞', logic: '电网设备龙头' },
                        ],
                    },
                    {
                        code: '880430', name: '航空', icon: '✈️',
                        desc: '航空运输，周期+成长',
                        logic: '受油价+汇率+出行需求驱动。油价是最大成本，汇率影响汇兑损益，出行复苏+国际航线恢复→供需改善。',
                        drivers: [
                            { icon: '🛢️', name: '油价', desc: '航油成本' },
                            { icon: '✈️', name: '出行复苏', desc: '客运量恢复' },
                            { icon: '💱', name: '汇率', desc: '汇兑损益' },
                        ],
                        upstream: [{ icon: '🛢️', name: '航油', desc: '航空成本' }],
                        downstream: [{ icon: '👤', name: '旅客', desc: '航空出行' }],
                        stocks: [
                            { code: '600029', name: '南方航空', logic: '航空龙头' },
                            { code: '601111', name: '中国国航', logic: '国际航线' },
                        ],
                    },
                    {
                        code: '880431', name: '船舶', icon: '🛳️',
                        desc: '造船+航运装备',
                        logic: '受全球运力需求+新船订单周期驱动。航运景气→船东下单→船厂订单饱满，船舶周期上行，军船/海工也有看点。',
                        drivers: [
                            { icon: '🚢', name: '航运景气', desc: '运价→新船订单' },
                            { icon: '🛠️', name: '船舶周期', desc: '造船产能紧张' },
                            { icon: '🎖️', name: '军船', desc: '海军装备' },
                        ],
                        upstream: [{ icon: '🔩', name: '钢板/船用设备', desc: '造船原料' }],
                        downstream: [{ icon: '🚢', name: '航运公司', desc: '船舶采购' }],
                        stocks: [
                            { code: '600150', name: '中国船舶', logic: '造船龙头' },
                            { code: '601989', name: '中国重工', logic: '造船+军工' },
                        ],
                    },
                ],
            },
            {
                id: 'finance', name: '金融地产', icon: '🏦',
                industries: [
                    {
                        code: '880471', name: '银行', icon: '🏦',
                        desc: '商业银行，高股息',
                        logic: '银行看净息差+资产质量+信贷需求。息差受LPR/存款利率影响，地产风险出清改善资产质量。高股息+低估值为防御配置。',
                        drivers: [
                            { icon: '📊', name: '净息差', desc: '存贷利差' },
                            { icon: '🏠', name: '地产风险', desc: '资产质量' },
                            { icon: '📈', name: '信贷需求', desc: '社融/投放' },
                        ],
                        upstream: [{ icon: '👤', name: '存款', desc: '银行负债' }],
                        downstream: [{ icon: '🏢', name: '企业/居民', desc: '信贷投放' }],
                        stocks: [
                            { code: '600036', name: '招商银行', logic: '零售银行龙头' },
                            { code: '601398', name: '工商银行', logic: '国有大行' },
                            { code: '601166', name: '兴业银行', logic: '股份行' },
                        ],
                    },
                    {
                        code: '880472', name: '证券', icon: '📈',
                        desc: '券商，牛市旗手',
                        logic: '券商看市场成交+投行+自营。市场活跃→经纪/两融收入，注册制→投行，政策利好（并购重组）催化。',
                        drivers: [
                            { icon: '📈', name: '市场成交', desc: '成交量/两融' },
                            { icon: '🏦', name: '投行业务', desc: 'IPO/再融资' },
                            { icon: '🤝', name: '并购重组', desc: '券商整合' },
                        ],
                        upstream: [{ icon: '📊', name: '市场行情', desc: '券商盈利基础' }],
                        downstream: [{ icon: '👤', name: '投资者', desc: '经纪/两融' }],
                        stocks: [
                            { code: '600030', name: '中信证券', logic: '券商龙头' },
                            { code: '601688', name: '华泰证券', logic: '综合券商' },
                            { code: '300059', name: '东方财富', logic: '互联网券商' },
                        ],
                    },
                    {
                        code: '880473', name: '保险', icon: '🛡️',
                        desc: '寿险+财险，长端利率',
                        logic: '保险看负债端（保费）+资产端（投资）。长端利率决定投资收益，新单保费增长，代理人改革提质。',
                        drivers: [
                            { icon: '📉', name: '长端利率', desc: '投资收益' },
                            { icon: '📊', name: '保费收入', desc: 'NBV增长' },
                            { icon: '👤', name: '代理人改革', desc: '产能提升' },
                        ],
                        upstream: [{ icon: '💵', name: '投资资产', desc: '险资配置' }],
                        downstream: [{ icon: '👤', name: '投保人', desc: '保费' }],
                        stocks: [
                            { code: '601318', name: '中国平安', logic: '综合金融龙头' },
                            { code: '601628', name: '中国人寿', logic: '寿险龙头' },
                        ],
                    },
                    {
                        code: '880474', name: '多元金融', icon: '💳',
                        desc: '信托/租赁/期货',
                        logic: '多元金融看政策+子行业景气。信托转型，租赁看制造业，期货看商品活跃度，互联网金融科技。',
                        drivers: [
                            { icon: '📜', name: '政策', desc: '金融监管' },
                            { icon: '🏭', name: '租赁需求', desc: '设备租赁' },
                            { icon: '📊', name: '期货活跃', desc: '商品市场' },
                        ],
                        upstream: [{ icon: '💵', name: '资金', desc: '金融杠杆' }],
                        downstream: [{ icon: '🏢', name: '企业/个人', desc: '金融服务' }],
                        stocks: [
                            { code: '600816', name: '安信信托', logic: '信托' },
                            { code: '600901', name: '江苏金租', logic: '金融租赁' },
                        ],
                    },
                    {
                        code: '880476', name: '建筑', icon: '🏗️',
                        desc: '建筑工程，基建主力',
                        logic: '建筑看基建投资+地产+海外工程。基建稳增长抓手，订单转化收入，央企低估值高股息。',
                        drivers: [
                            { icon: '🏗️', name: '基建投资', desc: '稳增长' },
                            { icon: '🌍', name: '海外工程', desc: '一带一路' },
                            { icon: '💵', name: '订单', desc: '新签订单' },
                        ],
                        upstream: [{ icon: '🔩', name: '钢材/水泥', desc: '建材' }],
                        downstream: [{ icon: '🏗️', name: '政府/地产', desc: '工程发包' }],
                        stocks: [
                            { code: '601668', name: '中国建筑', logic: '建筑央企' },
                            { code: '601390', name: '中国中铁', logic: '基建龙头' },
                        ],
                    },
                    {
                        code: '880482', name: '房地产', icon: '🏠',
                        desc: '房地产开发+服务',
                        logic: '地产看政策+销售+资金。政策宽松（限购/利率）→销售回暖→拿地开工。行业出清后格局改善，央国企受益。',
                        drivers: [
                            { icon: '📜', name: '政策', desc: '限购/降首付' },
                            { icon: '📈', name: '销售', desc: '商品房成交' },
                            { icon: '💰', name: '融资', desc: '信用/资金' },
                        ],
                        upstream: [{ icon: '🏗️', name: '土地/建材', desc: '开发成本' }],
                        downstream: [{ icon: '👤', name: '购房者', desc: '商品房需求' }],
                        stocks: [
                            { code: '600048', name: '保利发展', logic: '央企地产龙头' },
                            { code: '000002', name: '万科A', logic: '地产龙头' },
                        ],
                    },
                ],
            },
            {
                id: 'utility', name: '公用交运', icon: '🚉',
                industries: [
                    {
                        code: '880305', name: '电力', icon: '⚡',
                        desc: '火电+水电+核电+新能源',
                        logic: '电力看电量+电价+成本。火电看煤价（成本下降盈利改善），水电看来水，核电稳定，新能源装机增长。',
                        drivers: [
                            { icon: '⚡', name: '电价', desc: '市场化电价' },
                            { icon: '⛏️', name: '煤价', desc: '火电成本' },
                            { icon: '🌊', name: '来水', desc: '水电出力' },
                        ],
                        upstream: [{ icon: '⛏️', name: '煤炭', desc: '火电燃料' }],
                        downstream: [{ icon: '🏭', name: '工商业/居民', desc: '用电需求' }],
                        stocks: [
                            { code: '600900', name: '长江电力', logic: '水电龙头' },
                            { code: '601985', name: '中国核电', logic: '核电龙头' },
                            { code: '600011', name: '华能国际', logic: '火电龙头' },
                        ],
                    },
                    {
                        code: '880453', name: '公共交通', icon: '🚌',
                        desc: '公交+水务+燃气',
                        logic: '公用事业，防御属性。水务/燃气看价改+量增，公交看运营补贴。现金流稳定，高股息。',
                        drivers: [
                            { icon: '📜', name: '价格改革', desc: '水/气价上调' },
                            { icon: '👥', name: '人口增长', desc: '用水用气量' },
                            { icon: '💵', name: '运营补贴', desc: '公交补贴' },
                        ],
                        upstream: [{ icon: '🌊', name: '水源/气源', desc: '公用原料' }],
                        downstream: [{ icon: '👤', name: '居民/企业', desc: '公共需求' }],
                        stocks: [
                            { code: '600323', name: '瀚蓝环境', logic: '环保+水务' },
                            { code: '600635', name: '大众公用', logic: '燃气+公用' },
                        ],
                    },
                    {
                        code: '880456', name: '环境保护', icon: '🌿',
                        desc: '环保工程+运营',
                        logic: '环保看政策+订单+运营现金流。双碳政策驱动，垃圾焚烧/危废运营稳定，检测/节能成长。',
                        drivers: [
                            { icon: '🌿', name: '双碳政策', desc: '环保投入' },
                            { icon: '🏭', name: '运营项目', desc: '垃圾焚烧' },
                            { icon: '🔬', name: '检测/节能', desc: '成长业务' },
                        ],
                        upstream: [{ icon: '🔧', name: '环保设备', desc: '治理装备' }],
                        downstream: [{ icon: '🏭', name: '工业企业', desc: '环保服务' }],
                        stocks: [
                            { code: '300070', name: '碧水源', logic: '水务环保' },
                            { code: '603568', name: '伟明环保', logic: '垃圾焚烧' },
                        ],
                    },
                    {
                        code: '880459', name: '运输服务', icon: '🚚',
                        desc: '铁路/公路/港口/物流',
                        logic: '运输看货量+运价+成本。港口看进出口，公路/铁路看货运量，物流看电商，高股息防御。',
                        drivers: [
                            { icon: '📦', name: '物流需求', desc: '电商/制造业' },
                            { icon: '🌍', name: '进出口', desc: '港口吞吐' },
                            { icon: '🚚', name: '货运量', desc: '公路/铁路' },
                        ],
                        upstream: [{ icon: '⛽', name: '燃油/车辆', desc: '运输成本' }],
                        downstream: [{ icon: '🏭', name: '制造业/贸易', desc: '运输需求' }],
                        stocks: [
                            { code: '601006', name: '大秦铁路', logic: '铁路货运' },
                            { code: '600018', name: '上港集团', logic: '港口龙头' },
                            { code: '600233', name: '圆通速递', logic: '快递物流' },
                        ],
                    },
                    {
                        code: '880452', name: '电信运营', icon: '📡',
                        desc: '运营商+通信服务',
                        logic: '运营商看用户+ARPU+资本开支。5G用户增长，云计算/数字化第二曲线，高股息。',
                        drivers: [
                            { icon: '📱', name: '5G用户', desc: '渗透率' },
                            { icon: '☁️', name: '云计算', desc: '产业数字化' },
                            { icon: '💵', name: '分红', desc: '高股息' },
                        ],
                        upstream: [{ icon: '📡', name: '通信设备', desc: '网络建设' }],
                        downstream: [{ icon: '👤', name: '用户', desc: '通信服务' }],
                        stocks: [
                            { code: '600941', name: '中国移动', logic: '运营商龙头' },
                            { code: '600050', name: '中国联通', logic: '运营商' },
                        ],
                    },
                ],
            },
        ]);

        const curSector = computed(() => {
            for (const g of sectorGroups.value) {
                const found = g.industries.find(i => i.code === activeSector.value);
                if (found) return found;
            }
            return null;
        });

        return {
            events, activeEvent, ev, switchEvent, timingLabel, goStock,
            viewMode, sectorGroups, activeSector, curSector,
        };
    },
});

app.mount('#app');

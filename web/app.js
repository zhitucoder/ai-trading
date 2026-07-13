const { createApp, ref, reactive, computed, onMounted, nextTick, watch } = Vue;

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
            { id: 'screening', label: '选股策略', icon: '⊞' },
            { id: 'vcp', label: 'VCP波动收缩', icon: '◐' },
            { id: 'bt_strategies', label: '回测策略', icon: '⇄' },
            { id: 'profile', label: '股票画像', icon: '◈' },
            { id: 'debate', label: 'AI多空辩论', icon: '⚖' },
            { id: 'expert', label: '蒸馏专家', icon: '⚗' },
            { id: 'query', label: '智能问数', icon: '✦' },
            { id: 'data_mgmt', label: '数据管理', icon: '⚙' },
        ];
        const navPages = computed(() => pages);
        return { currentPage, pages, navPages };
    },
});

app.component('screening-page', {
    template: '#screening-tpl',
    setup() {
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

        function selectStrategy(id) { selectedStrategy.value = id; result.value = null; error.value = ''; }

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
            const params = new URLSearchParams();
            params.set('strategy_id', selectedStrategy.value);
            params.set('ma_periods', maPeriods.value);
            params.set('revenue_threshold', revenueThreshold.value);
            params.set('profit_threshold', profitThreshold.value);
            params.set('debt_threshold', debtThreshold.value);
            params.set('consolidation_days', consolidationDays.value);
            try {
                const r = await fetch(`${API_BASE}/screening/execute?${params}`, { method: 'POST' });
                const data = await r.json();
                if (data.error) error.value = data.error; else result.value = data;
            } catch (e) { error.value = '请求失败: ' + e.message; }
            finally { loading.value = false; }
        }

        function isSelected(id) { return selectedStrategy.value === id; }

        return {
            strategies, tabType, selectedStrategy, loading, result, error,
            maPeriods, consolidationDays, revenueThreshold, profitThreshold, debtThreshold,
            currentStrategies, hasResult,
            selectStrategy, execute, isSelected, switchToTurnaround,
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

        async function loadProfile() {
            if (!stockCode.value) return;
            loading.value = true;
            error.value = '';
            profile.value = null;
            try {
                    const r = await fetch(`${API_BASE}/profile/${stockCode.value}?refresh=true`);
                const data = await r.json();
                if (data.error) error.value = data.error;
                else profile.value = data;
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

        function goToProfile(code) {
            stockCode.value = code;
            activeTab.value = 'single';
            loadProfile();
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
        const filterDebtMax = ref(null);
        const filterGmGrowthQ = ref(null);
        const filterGmGrowth2y = ref(null);
        const filterContractLiabMin = ref(null);
        const filterContractLiabMax = ref(null);
        const growthTagOptions = [
            { id: 'biz.annual_rev_growth_1y', label: '营收连增1年' },
            { id: 'biz.annual_rev_growth_2y', label: '营收连增2年' },
            { id: 'biz.annual_rev_growth_3y', label: '营收连增3年' },
            { id: 'biz.annual_rev_growth_4y', label: '营收连增4年' },
            { id: 'biz.annual_profit_growth_1y', label: '利润连增1年' },
            { id: 'biz.annual_profit_growth_2y', label: '利润连增2年' },
            { id: 'biz.annual_profit_growth_3y', label: '利润连增3年' },
            { id: 'biz.annual_profit_growth_4y', label: '利润连增4年' },
            { id: 'biz.annual_gm_improve_1y', label: '毛利率提升1年' },
            { id: 'biz.annual_gm_improve_2y', label: '毛利率连升2年' },
            { id: 'biz.annual_gm_improve_3y', label: '毛利率连升3年' },
            { id: 'biz.annual_gm_improve_4y', label: '毛利率连升4年' },
        ];
        const selectedGrowthTags = ref([]);
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
                const body = {
                    stages: selectedStages.value,
                    tags: { must: selectedGrowthTags.value, must_not: [], any: [] },
                    tech_score_min: filterTechScore.value > 0 ? filterTechScore.value : null,
                    fund_score_min: filterFundScore.value > 0 ? filterFundScore.value : null,
                    revenue_growth_min: filterRevGrowth.value || null,
                    net_profit_growth_min: filterProfitGrowth.value || null,
                    debt_ratio_max: filterDebtMax.value || null,
                    gm_growth_q_min: filterGmGrowthQ.value || null,
                    gm_growth_2y_min: filterGmGrowth2y.value || null,
                    contract_liab_min: filterContractLiabMin.value || null,
                    contract_liab_max: filterContractLiabMax.value || null,
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
                if (!data.error) searchResult.value = data;
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
            filterDebtMax.value = null;
            filterGmGrowthQ.value = null;
            filterGmGrowth2y.value = null;
            filterContractLiabMin.value = null;
            filterContractLiabMax.value = null;
            selectedGrowthTags.value = [];
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

        onMounted(() => {
            loadProfile();
            loadStatus();
            checkRunningRefresh();
        });

        return {
            activeTab, stockCode, loading, profile, error,
            loadProfile, scoreClass, scoreTextClass, rsiClass, debtClass, gmTrendClass, goToProfile,
            stageOptions, selectedStages, filterTechScore, filterFundScore,
            filterRevGrowth, filterProfitGrowth, filterDebtMax,
            filterGmGrowthQ, filterGmGrowth2y,
            filterContractLiabMin, filterContractLiabMax,
            growthTagOptions, selectedGrowthTags,
            searchLoading, searchResult, profileStatusData, sortBy, sortOrder,
            refreshing, refreshProgress, refreshToast,
            toggleStage, toggleGrowthTag, onFilterChange, doSearch, resetFilters, triggerRefresh,
            toggleSort, sortArrow,
            fmt, fmtGrowth, fmtMoney, valClass,
        };
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

        onMounted(loadStatus);

        return {
            status, klineLoading, klineResult, klineError,
            finLoading, finResult, finError,
            lastSyncLabel, finDotClass, finStatusText,
            updateKline, updateFinancial,
        };
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

app.component('placeholder-page', {
    props: ['page'],
    template: '<div class="placeholder"><div class="big-icon">{{ icon }}</div><p>{{ page.label }}</p><p>功能开发中...</p></div>',
    computed: {
        icon() { return this.page.icon || '⊡'; },
    },
});

app.mount('#app');

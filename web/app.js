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
            { id: 'position_bt', label: '建仓回测', icon: '⟳' },
            { id: 'ma_bt', label: '均线回测', icon: '∿' },
            { id: 'profile', label: '股票画像', icon: '◈' },
            { id: 'debate', label: 'AI多空辩论', icon: '⚖' },
            { id: 'expert', label: '蒸馏专家', icon: '⚗' },
        ];
        return { currentPage, pages };
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

        async function execute() {
            if (!selectedStrategy.value) return;
            loading.value = true; error.value = ''; result.value = null;
            const params = new URLSearchParams();
            params.set('strategy_id', selectedStrategy.value);
            params.set('ma_periods', maPeriods.value);
            params.set('revenue_threshold', revenueThreshold.value);
            params.set('profit_threshold', profitThreshold.value);
            params.set('debt_threshold', debtThreshold.value);
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
            maPeriods, revenueThreshold, profitThreshold, debtThreshold,
            currentStrategies, hasResult,
            selectStrategy, execute, isSelected,
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
                const r = await fetch(`${API_BASE}/profile/${stockCode.value}`);
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
        const searchLoading = ref(false);
        const searchResult = ref(null);
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

        let searchDebounce = null;
        function onFilterChange() {
            if (searchDebounce) clearTimeout(searchDebounce);
            searchDebounce = setTimeout(doSearch, 400);
        }

        async function doSearch() {
            searchLoading.value = true;
            try {
                const body = {
                    stages: selectedStages.value,
                    tags: { must: [], must_not: [], any: [] },
                    tech_score_min: filterTechScore.value > 0 ? filterTechScore.value : null,
                    fund_score_min: filterFundScore.value > 0 ? filterFundScore.value : null,
                    revenue_growth_min: filterRevGrowth.value,
                    net_profit_growth_min: filterProfitGrowth.value,
                    debt_ratio_max: filterDebtMax.value,
                    page: searchResult.value ? searchResult.value.page : 1,
                    page_size: 50,
                    sort_by: 'tech_score',
                    sort_order: 'desc',
                };
                const r = await fetch(`${API_BASE}/profiles/search`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await r.json();
                if (!data.error) searchResult.value = data;
            } catch (e) {
                console.error(e);
            } finally {
                searchLoading.value = false;
            }
        }

        function resetFilters() {
            selectedStages.value = [];
            filterTechScore.value = 0;
            filterFundScore.value = 0;
            filterRevGrowth.value = null;
            filterProfitGrowth.value = null;
            filterDebtMax.value = null;
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
            loadProfile, scoreClass, scoreTextClass, rsiClass, debtClass, goToProfile,
            stageOptions, selectedStages, filterTechScore, filterFundScore,
            filterRevGrowth, filterProfitGrowth, filterDebtMax,
            searchLoading, searchResult, profileStatusData,
            refreshing, refreshProgress, refreshToast,
            toggleStage, onFilterChange, doSearch, resetFilters, triggerRefresh,
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

app.component('placeholder-page', {
    props: ['page'],
    template: '<div class="placeholder"><div class="big-icon">{{ icon }}</div><p>{{ page.label }}</p><p>功能开发中...</p></div>',
    computed: {
        icon() { return this.page.icon || '⊡'; },
    },
});

app.mount('#app');

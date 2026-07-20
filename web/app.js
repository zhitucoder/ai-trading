const { createApp, ref, reactive, computed, onMounted, nextTick, watch, provide, inject } = Vue;

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
            { id: 'debate', label: 'AI多空辩论', icon: '⚖' },
            { id: 'expert', label: '蒸馏专家', icon: '⚗' },
            { id: 'query', label: '智能问数', icon: '✦' },
            { id: 'data_mgmt', label: '数据管理', icon: '⚙' },
        ];
        const navPages = computed(() => pages);
        provide('currentPage', currentPage);
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
        const finChartLoading = ref(false);
        const finChartCanvas = ref(null);

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
            const xs = data.years.map((_, i) => pad.left + cw * i / (n - 1 || 1));

            const rMax = Math.max(...data.revenues) * 1.15;
            const pMin = Math.min(...data.profits) * 1.1;
            const pMax = Math.max(...data.profits) * 1.15;
            const pRange = pMax - pMin || 1;
            const gVals = data.growth_rates.filter(v => v != null);
            const gMin = Math.min(...gVals) * 1.1;
            const gMax = Math.max(...gVals) * 1.15;
            const gRange = gMax - gMin || 1;
            const priceMax = Math.max(...data.prices) * 1.15;

            function yRev(v) { return pad.top + ch * (1 - v / rMax); }
            function yProf(v) { return pad.top + ch * (1 - (v - pMin) / pRange); }
            function yGr(v) { return pad.top + ch * (1 - (v - gMin) / gRange); }
            function yPrice(v) { return pad.top + ch * (1 - v / priceMax); }

            // Grid lines
            ctx.strokeStyle = 'rgba(255,255,255,0.05)';
            ctx.lineWidth = 1*dpr;
            for (let i = 0; i <= 4; i++) {
                const y = pad.top + ch * i / 4;
                ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + cw, y); ctx.stroke();
            }

            // Revenue bars
            for (let i = 0; i < n; i++) {
                const x = xs[i] - 14*dpr, w = 28*dpr;
                const h = ch * data.revenues[i] / rMax;
                ctx.fillStyle = 'rgba(100,149,237,0.45)';
                ctx.fillRect(x, pad.top + ch - h, w, h);
            }

            // Net profit line
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

            // Growth rate dashed line
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

            // Price line
            ctx.beginPath();
            ctx.strokeStyle = '#4ecdc4'; ctx.lineWidth = 2*dpr;
            for (let i = 0; i < n; i++) {
                const v = data.prices[i];
                if (v == null || v === 0) continue;
                const y = yPrice(v);
                i === 0 || data.prices[i-1] == null || data.prices[i-1] === 0 ? ctx.moveTo(xs[i], y) : ctx.lineTo(xs[i], y);
            }
            ctx.stroke();
            ctx.fillStyle = '#4ecdc4';
            for (let i = 0; i < n; i++) {
                const v = data.prices[i];
                if (v == null || v === 0) continue;
                ctx.beginPath(); ctx.arc(xs[i], yPrice(v), 3*dpr, 0, Math.PI*2); ctx.fill();
            }

            // ── Y axis labels (left: revenue/price) ──
            ctx.fillStyle = '#666'; ctx.font = `${10*dpr}px sans-serif`; ctx.textAlign = 'right';
            for (let i = 0; i <= 4; i++) {
                const v = Math.round(rMax * i / 4);
                ctx.fillText(v + '亿', pad.left - 6*dpr, pad.top + ch * (1 - i/4) + 4*dpr);
            }

            // ── Y axis right (growth rate) ──
            ctx.textAlign = 'left';
            for (let i = 0; i <= 4; i++) {
                const v = Math.round(gMin + gRange * i / 4);
                ctx.fillText(v + '%', pad.left + cw + 6*dpr, pad.top + ch * (1 - i/4) + 4*dpr);
            }

            // X labels
            ctx.fillStyle = '#999'; ctx.font = `${11*dpr}px sans-serif`; ctx.textAlign = 'center';
            for (let i = 0; i < n; i++) {
                ctx.fillText(data.years[i], xs[i], H - pad.bottom + 16*dpr);
            }

            // Legend
            const legend = [
                {label:'营收',color:'rgba(100,149,237,0.7)'},{label:'净利润',color:'#ffd700'},
                {label:'增长率',color:'#ff6b6b'},{label:'股价',color:'#4ecdc4'},
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

            // ── Hover tooltip ──
            const chartData = { data, xs, pad, cw, n, yProf, yGr, yPrice, rMax };
            canvas.chartData = chartData;

            canvas.onmousemove = function(e) {
                const cr = canvas.getBoundingClientRect();
                const mx = (e.clientX - cr.left) * dpr;
                const my = (e.clientY - cr.top) * dpr;
                const cd = canvas.chartData;
                if (!cd) return;

                // Find nearest year index
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
                const price = d.prices[idx];

                let html = `<div style="color:#ffd700;font-weight:700;margin-bottom:4px;">${yr}年</div>`;
                html += `<div><span style="color:#6495ed;">营收</span> ${rev.toFixed(1)}亿</div>`;
                html += `<div><span style="color:#ffd700;">净利润</span> ${prof.toFixed(2)}亿</div>`;
                html += `<div><span style="color:#ff6b6b;">增长率</span> ${gr != null ? (gr >= 0 ? '+' : '') + gr.toFixed(1) + '%' : 'N/A'}</div>`;
                html += `<div><span style="color:#4ecdc4;">均价</span> ${price > 0 ? price.toFixed(2) + '元' : 'N/A'}</div>`;
                tooltip.innerHTML = html;

                // Position tooltip
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
            if (window._profileStockCode) {
                stockCode.value = window._profileStockCode;
                window._profileStockCode = null;
            }
            loadProfile();
            loadStatus();
            checkRunningRefresh();
        });

        return {
            activeTab, stockCode, loading, profile, error, finChartLoading, finChartCanvas,
            loadProfile, loadFinChart, scoreClass, scoreTextClass, rsiClass, debtClass, gmTrendClass, goToProfile,
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

app.component('placeholder-page', {
    props: ['page'],
    template: '<div class="placeholder"><div class="big-icon">{{ icon }}</div><p>{{ page.label }}</p><p>功能开发中...</p></div>',
    computed: {
        icon() { return this.page.icon || '⊡'; },
    },
});

app.mount('#app');

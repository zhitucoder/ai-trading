const { createApp, ref, reactive, computed, onMounted } = Vue;

const API_BASE = '/api';

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

// ── Screening Component ──
app.component('screening-page', {
    template: '#screening-tpl',
    setup() {
        const strategies = ref({ technical: [], fundamental: [], combined: [] });
        const tabType = ref('technical');
        const selectedStrategy = ref(null);
        const loading = ref(false);
        const result = ref(null);
        const error = ref('');

        // Config
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

        const currentStrategies = computed(() => {
            return strategies.value[tabType.value] || [];
        });

        const hasResult = computed(() => result.value && result.value.rows && result.value.rows.length > 0);

        function selectStrategy(id) {
            selectedStrategy.value = id;
            result.value = null;
            error.value = '';
        }

        async function execute() {
            if (!selectedStrategy.value) return;
            loading.value = true;
            error.value = '';
            result.value = null;

            const params = new URLSearchParams();
            params.set('strategy_id', selectedStrategy.value);
            params.set('ma_periods', maPeriods.value);
            params.set('revenue_threshold', revenueThreshold.value);
            params.set('profit_threshold', profitThreshold.value);
            params.set('debt_threshold', debtThreshold.value);

            try {
                const r = await fetch(`${API_BASE}/screening/execute?${params}`, { method: 'POST' });
                const data = await r.json();
                if (data.error) {
                    error.value = data.error;
                } else {
                    result.value = data;
                }
            } catch (e) {
                error.value = '请求失败: ' + e.message;
            } finally {
                loading.value = false;
            }
        }

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

        function isSelected(id) {
            return selectedStrategy.value === id;
        }

        return {
            strategies, tabType, selectedStrategy, loading, result, error,
            maPeriods, revenueThreshold, profitThreshold, debtThreshold,
            currentStrategies, hasResult,
            selectStrategy, execute, fmt, fmtGrowth, fmtMoney, valClass, isSelected,
        };
    },
});

app.component('placeholder-page', {
    props: ['page'],
    template: '<div class="placeholder"><div class="big-icon">{{ icon }}</div><p>{{ page.label }}</p><p>功能开发中...</p></div>',
    computed: {
        icon() {
            return this.page.icon || '⊡';
        },
    },
});

app.mount('#app');

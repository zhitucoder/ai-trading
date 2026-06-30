const { createApp, ref, computed } = Vue;

const API_BASE = '';

const app = createApp({
  setup() {
    const currentPage = ref('screening');
    const loading = ref(false);
    const error = ref('');

    const navItems = [
      { key: 'screening', label: '选股策略', icon: '&#9670;' },
      { key: 'backtest', label: '建仓回测', icon: '&#8617;' },
      { key: 'profile', label: '股票画像', icon: '&#9673;' },
      { key: 'debate', label: 'AI多空辩论', icon: '&#9889;' },
      { key: 'expert', label: '蒸馏专家', icon: '&#9829;' },
    ];

    const screenTabs = [
      { key: 'technical', label: '技术指标选股' },
      { key: 'fundamental', label: '基本面选股' },
      { key: 'combined', label: '综合选股' },
    ];

    const activeScreenTab = ref('technical');

    const techParams = ref({
      maPeriods: [5, 10, 20, 60],
    });

    const fundParams = ref({
      revenueGrowthMin: 20,
      netProfitGrowthMin: 20,
      debtAssetRatioMax: 50,
    });

    const combinedParams = ref({
      maPeriods: [5, 10, 20, 60],
      revenueGrowthMin: 20,
      netProfitGrowthMin: 20,
      debtAssetRatioMax: 50,
    });

    const techResults = ref([]);
    const fundResults = ref([]);
    const combinedResults = ref([]);

    async function apiPost(url, body) {
      loading.value = true;
      error.value = '';
      try {
        const resp = await fetch(API_BASE + url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const json = await resp.json();
        if (json.code !== 0) throw new Error(json.detail || '请求失败');
        return json;
      } catch (e) {
        error.value = e.message;
        throw e;
      } finally {
        loading.value = false;
      }
    }

    async function runTechnical() {
      const res = await apiPost('/api/screen/technical', {
        ma_periods: techParams.value.maPeriods,
        bullish: true,
      });
      techResults.value = res.data;
    }

    async function runFundamental() {
      const res = await apiPost('/api/screen/fundamental', {
        revenue_growth_min: fundParams.value.revenueGrowthMin || null,
        net_profit_growth_min: fundParams.value.netProfitGrowthMin || null,
        debt_asset_ratio_max: fundParams.value.debtAssetRatioMax || null,
      });
      fundResults.value = res.data;
    }

    async function runCombined() {
      const res = await apiPost('/api/screen/combined', {
        ma_periods: combinedParams.value.maPeriods,
        revenue_growth_min: combinedParams.value.revenueGrowthMin,
        net_profit_growth_min: combinedParams.value.netProfitGrowthMin,
        debt_asset_ratio_max: combinedParams.value.debtAssetRatioMax,
      });
      combinedResults.value = res.data;
    }

    function formatMarketCap(val) {
      if (!val) return '-';
      if (val >= 1e8) return (val / 1e8).toFixed(2) + '亿';
      if (val >= 1e4) return (val / 1e4).toFixed(2) + '万';
      return val;
    }

    return {
      currentPage,
      loading,
      error,
      navItems,
      screenTabs,
      activeScreenTab,
      techParams,
      fundParams,
      combinedParams,
      techResults,
      fundResults,
      combinedResults,
      runTechnical,
      runFundamental,
      runCombined,
      formatMarketCap,
    };
  },
});

app.mount('#app');

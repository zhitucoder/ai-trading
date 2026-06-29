<template>
  <div class="app-container">
    <header class="header">
      <h1>AI-TRADING 选股系统</h1>
      <p class="subtitle">A 股量化筛选 · 技术面 + 基本面</p>
    </header>

    <section class="filters">
      <div class="filter-group">
        <label class="switch-label">
          <input type="checkbox" v-model="filters.ma_bullish" />
          <span class="switch"></span>
          均线多头排列 <small>MA5 &gt; MA10 &gt; MA20 &gt; MA60 &gt; MA120</small>
        </label>
      </div>

      <div class="filter-group">
        <label>营收增长率 &ge; <input type="number" v-model.number="filters.min_revenue_growth" class="num-input" /> %</label>
      </div>

      <div class="filter-group">
        <label>净利润增长率 &ge; <input type="number" v-model.number="filters.min_net_profit_growth" class="num-input" /> %</label>
      </div>

      <div class="filter-group">
        <label>资产负债率 &le; <input type="number" v-model.number="filters.max_debt_ratio" class="num-input" /> %</label>
      </div>

      <button class="btn-primary" @click="doScreen" :disabled="loading">
        {{ loading ? '筛选中...' : '开始筛选' }}
      </button>
    </section>

    <section class="result-bar">
      <span v-if="result.total !== null">共 <strong>{{ result.total }}</strong> 只股票符合条件</span>
      <span v-if="error" class="error">{{ error }}</span>
    </section>

    <section class="table-wrap">
      <table v-if="result.stocks.length">
        <thead>
          <tr>
            <th>代码</th>
            <th>名称</th>
            <th class="num">最新价</th>
            <th class="num">MA5</th>
            <th class="num">MA10</th>
            <th class="num">MA20</th>
            <th class="num">MA60</th>
            <th class="num">MA120</th>
            <th class="num">营收增长</th>
            <th class="num">净利增长</th>
            <th class="num">负债率</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in result.stocks" :key="s.stock_code">
            <td class="code">{{ s.stock_code }}</td>
            <td class="name">{{ s.stock_name }}</td>
            <td class="num">{{ s.price }}</td>
            <td class="num" :class="s.ma5 > s.ma10 ? 'bull' : ''">{{ s.ma5 }}</td>
            <td class="num" :class="s.ma10 > s.ma20 ? 'bull' : ''">{{ s.ma10 }}</td>
            <td class="num" :class="s.ma20 > s.ma60 ? 'bull' : ''">{{ s.ma20 }}</td>
            <td class="num" :class="s.ma60 > s.ma120 ? 'bull' : ''">{{ s.ma60 }}</td>
            <td class="num">{{ s.ma120 }}</td>
            <td class="num green">{{ s.revenue_growth }}%</td>
            <td class="num green">{{ s.net_profit_growth }}%</td>
            <td class="num">{{ s.debt_ratio }}%</td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="result.total === 0" class="empty">无匹配结果</div>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'

const API = 'http://127.0.0.1:9000'

const filters = reactive({
  ma_bullish: true,
  min_revenue_growth: 20,
  min_net_profit_growth: null,
  max_debt_ratio: 50,
})

const loading = ref(false)
const error = ref('')
const result = reactive({ total: null, stocks: [] })

async function doScreen() {
  loading.value = true
  error.value = ''
  result.total = null
  result.stocks = []

  const params = new URLSearchParams()
  params.set('ma_bullish', filters.ma_bullish)
  if (filters.min_revenue_growth != null) params.set('min_revenue_growth', filters.min_revenue_growth)
  if (filters.min_net_profit_growth != null) params.set('min_net_profit_growth', filters.min_net_profit_growth)
  if (filters.max_debt_ratio != null) params.set('max_debt_ratio', filters.max_debt_ratio)
  params.set('limit', '200')

  try {
    const res = await fetch(`${API}/api/screen?${params}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    result.total = data.total
    result.stocks = data.stocks
  } catch (e) {
    error.value = '请求失败: ' + e.message
  } finally {
    loading.value = false
  }
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: #0a0e17;
  color: #c8d6e5;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  min-height: 100vh;
}
.app-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 24px;
}

.header { margin-bottom: 32px; }
.header h1 {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 3px;
  color: #00d4aa;
  text-shadow: 0 0 12px rgba(0, 212, 170, .3);
}
.subtitle {
  font-size: 12px;
  color: #5a6a7a;
  margin-top: 4px;
}

.filters {
  background: #111927;
  border: 1px solid #1e2a3a;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
}
.filter-group { font-size: 13px; }
.switch-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.switch-label input { display: none; }
.switch {
  width: 36px;
  height: 20px;
  background: #1e2a3a;
  border-radius: 10px;
  position: relative;
  transition: .2s;
}
.switch::after {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  background: #5a6a7a;
  border-radius: 50%;
  top: 2px;
  left: 2px;
  transition: .2s;
}
.switch-label input:checked + .switch { background: #00d4aa; }
.switch-label input:checked + .switch::after { left: 18px; background: #fff; }
.num-input {
  width: 70px;
  background: #0a0e17;
  border: 1px solid #1e2a3a;
  border-radius: 4px;
  color: #00d4aa;
  padding: 4px 6px;
  font-size: 13px;
  font-family: inherit;
  text-align: center;
}
.num-input:focus { outline: none; border-color: #00d4aa; }
small { color: #5a6a7a; margin-left: 4px; }

.btn-primary {
  background: #00d4aa;
  color: #0a0e17;
  border: none;
  border-radius: 6px;
  padding: 8px 24px;
  font-weight: 700;
  font-size: 13px;
  cursor: pointer;
  transition: .2s;
  font-family: inherit;
}
.btn-primary:hover { box-shadow: 0 0 16px rgba(0, 212, 170, .4); }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }

.result-bar {
  margin: 16px 0;
  font-size: 13px;
}
.error { color: #e74c3c; }

.table-wrap {
  background: #111927;
  border: 1px solid #1e2a3a;
  border-radius: 8px;
  overflow-x: auto;
}
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th {
  background: #0d1520;
  color: #5a6a7a;
  font-weight: 600;
  padding: 10px 12px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #1e2a3a;
}
td {
  padding: 8px 12px;
  border-bottom: 1px solid #141e2c;
  white-space: nowrap;
}
tr:hover td { background: #141e2c; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.code { color: #00d4aa; font-weight: 600; }
.name { color: #c8d6e5; }
.green { color: #2ecc71; }
.bull { color: #00d4aa !important; }
.empty {
  padding: 40px;
  text-align: center;
  color: #5a6a7a;
}
</style>

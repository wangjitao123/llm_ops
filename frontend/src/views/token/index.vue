<template>
  <div class="page-container">
    <!-- 筛选工具条 -->
    <div class="panel-card">
      <div class="table-toolbar">
        <div class="toolbar-filters">
          <a-select v-model:value="query.dimension_type" style="width: 130px" @change="loadStats">
            <a-select-option value="model">按模型</a-select-option>
            <a-select-option value="key">按 Key</a-select-option>
            <a-select-option value="application">按应用</a-select-option>
          </a-select>
          <a-range-picker v-model:value="dateRange" />
          <a-select v-model:value="query.granularity" style="width: 100px">
            <a-select-option value="daily">按天</a-select-option>
            <a-select-option value="hourly">按小时</a-select-option>
          </a-select>
          <a-button type="primary" @click="loadStats">
            <template #icon><SearchOutlined /></template>
            查询
          </a-button>
        </div>
        <div class="toolbar-actions">
          <a-button @click="exportReport"><template #icon><DownloadOutlined /></template>导出报表</a-button>
        </div>
      </div>
    </div>

    <!-- 统计卡 -->
    <a-row :gutter="[16, 16]" style="margin-top: 16px">
      <a-col :xs="12" :sm="8" :lg="6">
        <StatCard label="总 Token 消耗" :value="totalTokensSafe" :icon="ThunderboltOutlined" color="#1890ff" :formatter="(n: number) => formatTokenCount(n)" />
      </a-col>
      <a-col :xs="12" :sm="8" :lg="6">
        <StatCard label="总费用 (¥)" :value="totalCostSafe" :icon="AccountBookOutlined" color="#faad14" :precision="4" />
      </a-col>
      <a-col :xs="12" :sm="8" :lg="6">
        <StatCard label="请求总量" :value="totalRequests" :icon="ApiOutlined" color="#52c41a" suffix=" 次" />
      </a-col>
      <a-col :xs="12" :sm="8" :lg="6">
        <StatCard label="维度项数" :value="dimensionItems.length" :icon="BarsOutlined" color="#722ed1" suffix=" 项" />
      </a-col>
    </a-row>

    <!-- 用量趋势 -->
    <div class="panel-card" style="margin-top: 16px">
      <div class="panel-header">
        <span class="panel-title">用量趋势</span>
        <span class="legend-chip"><i style="background:#1890ff"></i>输入 <i style="background:#52c41a"></i>输出</span>
      </div>
      <div class="panel-body">
        <div ref="chartRef" style="height: 340px"></div>
      </div>
    </div>

    <!-- 维度明细 -->
    <div class="panel-card">
      <div class="panel-header">
        <span class="panel-title">维度明细</span>
      </div>
      <div class="panel-body padless">
        <a-table :data-source="dimensionItems" row-key="dimension_id" size="small" :pagination="{ pageSize: 10 }">
          <a-table-column title="维度" key="dimension_name">
            <template #default="{ record }">
              <a-space>
                <a-avatar size="small" style="background:#e6f7ff;color:#1890ff;font-size:13px">
                  {{ dimensionName(record.dimension_id)[0] }}
                </a-avatar>
                <span style="font-weight:500">{{ dimensionName(record.dimension_id) }}</span>
              </a-space>
            </template>
          </a-table-column>
          <a-table-column title="请求次数" data-index="request_count" key="request_count" />
          <a-table-column title="总 Token" data-index="total_tokens" key="total_tokens">
            <template #default="{ text }">{{ formatTokenCount(text) }}</template>
          </a-table-column>
          <a-table-column title="费用" data-index="total_cost" key="total_cost">
            <template #default="{ text }">¥{{ Number(text || 0).toFixed(6) }}</template>
          </a-table-column>
        </a-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, reactive, computed } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  SearchOutlined, DownloadOutlined,
  ThunderboltOutlined, AccountBookOutlined, ApiOutlined, BarsOutlined
} from '@ant-design/icons-vue'
import StatCard from '@/components/common/StatCard.vue'
import { getTokenStats, getTokenSummary, getCostReport } from '@/api/tokenApi'
import { getModelList } from '@/api/modelApi'
import { getKeyList, getApplicationList } from '@/api/keyApi'
import type { StatsResponse, ModelItem, KeyItem, ApplicationItem } from '@/types/api'
import { formatTokenCount } from '@/utils'

const query = reactive<{ dimension_type: string; granularity: 'daily' | 'hourly' }>({ dimension_type: 'model', granularity: 'daily' })
const dateRange = ref<[dayjs.Dayjs, dayjs.Dayjs]>([dayjs().subtract(6, 'day'), dayjs()])
const stats = ref<StatsResponse>({ dimension_type: 'model', points: [], total_tokens: 0, total_cost: 0 })
const dimensionItems = ref<any[]>([])
const chartRef = ref<HTMLDivElement>()
const modelList = ref<ModelItem[]>([])
const keyList = ref<KeyItem[]>([])
const appList = ref<ApplicationItem[]>([])

const totalRequests = computed(() => stats.value.points.reduce((sum, p) => sum + (p.request_count || 0), 0))
// Ant Design statistic formatter 会把对象传给 value，导致 Number(对象)=NaN；这里安全兜底
const totalTokensSafe = computed(() => stats.value.total_tokens ?? 0)
const totalCostSafe = computed(() => stats.value.total_cost ?? 0)

/** 维度 id → 名称：按当前维度类型映射（模型名/Key 名/应用名，取不到回退 id） */
function dimensionName(id: number): string {
  if (query.dimension_type === 'model') {
    return modelList.value.find((m) => m.id === id)?.name || `#${id}`
  }
  if (query.dimension_type === 'key') {
    const k = keyList.value.find((x) => x.id === id)
    return k ? `${k.name} (${k.key_prefix}…)` : `#${id}`
  }
  if (query.dimension_type === 'application') {
    return appList.value.find((a) => a.id === id)?.name || `#${id}`
  }
  return `#${id}`
}

function formatParams() {
  return {
    dimension_type: query.dimension_type,
    granularity: query.granularity,
    start_date: dateRange.value[0].format('YYYY-MM-DD'),
    end_date: dateRange.value[1].format('YYYY-MM-DD')
  }
}

async function loadStats() {
  try {
    const result = await getTokenStats(formatParams())
    stats.value = result
    renderChart()

    const summary = await getTokenSummary({
      start_date: dateRange.value[0].format('YYYY-MM-DD'),
      end_date: dateRange.value[1].format('YYYY-MM-DD'),
      dimension_type: query.dimension_type
    })
    dimensionItems.value = summary as any[]
  } catch {
    message.error('统计数据加载失败')
  }
}

function renderChart() {
  if (!chartRef.value) return
  chartInstance?.dispose()
  chartInstance = echarts.init(chartRef.value)
  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['输入 Token', '输出 Token'], top: 0 },
    grid: { left: 50, right: 16, top: 32, bottom: 8 },
    xAxis: { type: 'category', data: stats.value.points.map((p) => p.date) },
    yAxis: { type: 'value', name: 'Token' },
    series: [
      {
        name: '输入 Token',
        type: 'bar',
        stack: 'total',
        data: stats.value.points.map((p) => p.prompt_tokens),
        itemStyle: { color: '#1890ff', borderRadius: [0, 0, 0, 0] }
      },
      {
        name: '输出 Token',
        type: 'bar',
        stack: 'total',
        data: stats.value.points.map((p) => p.completion_tokens),
        itemStyle: { color: '#52c41a' }
      }
    ]
  })
  resizeHandler = () => chartInstance?.resize()
  window.addEventListener('resize', resizeHandler)
}

let chartInstance: echarts.ECharts | null = null
let resizeHandler: (() => void) | null = null

onUnmounted(() => {
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler)
    resizeHandler = null
  }
  chartInstance?.dispose()
  chartInstance = null
})

async function exportReport() {
  try {
    await getCostReport(formatParams())
    message.success('导出任务已提交，生成完成后可下载')
  } catch {
    message.error('导出失败')
  }
}

onMounted(async () => {
  try {
    modelList.value = (await getModelList()) as ModelItem[]
  } catch { /* 忽略 */ }
  try {
    keyList.value = (await getKeyList({ page: 1, size: 999 })) as KeyItem[]
  } catch { /* 忽略 */ }
  try {
    appList.value = (await getApplicationList()) as ApplicationItem[]
  } catch { /* 忽略 */ }
  loadStats()
})
</script>

<style scoped>
.legend-chip { font-size: 12px; color: #8c8c8c; display: inline-flex; gap: 12px; align-items: center; }
.legend-chip i { display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }
</style>

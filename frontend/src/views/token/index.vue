<template>
  <div class="page-container">
    <a-card>
      <a-space wrap>
        <a-select v-model:value="query.dimension_type" style="width: 130px">
          <a-select-option value="model">按模型</a-select-option>
          <a-select-option value="application">按应用</a-select-option>
          <a-select-option value="key">按 Key</a-select-option>
          <a-select-option value="user">按用户</a-select-option>
        </a-select>
        <a-range-picker v-model:value="dateRange" />
        <a-select v-model:value="query.granularity" style="width: 100px">
          <a-select-option value="daily">按天</a-select-option>
          <a-select-option value="hourly">按小时</a-select-option>
        </a-select>
        <a-button type="primary" @click="loadStats">查询</a-button>
        <a-button @click="exportReport">导出报表</a-button>
      </a-space>
    </a-card>

    <a-row :gutter="[16, 16]" style="margin-top: 16px">
      <a-col :xs="24" :sm="8">
        <a-card><a-statistic title="总 Token 消耗" :value="stats.total_tokens" :formatter="(v: any) => formatTokenCount(Number(v))" /></a-card>
      </a-col>
      <a-col :xs="24" :sm="8">
        <a-card><a-statistic title="总费用" :value="stats.total_cost" :precision="6" prefix="¥" /></a-card>
      </a-col>
      <a-col :xs="24" :sm="8">
        <a-card><a-statistic title="请求总量" :value="totalRequests" /></a-card>
      </a-col>
    </a-row>

    <a-card title="用量趋势" style="margin-top: 16px">
      <div ref="chartRef" style="height: 360px"></div>
    </a-card>

    <a-card title="维度明细" style="margin-top: 16px">
      <a-table :data-source="dimensionItems" row-key="dimension_id" size="small" :pagination="{ pageSize: 10 }">
        <a-table-column title="维度" key="dimension_name" />
        <a-table-column title="请求次数" data-index="request_count" key="request_count" />
        <a-table-column title="总 Token" data-index="total_tokens" key="total_tokens">
          <template #default="{ text }">{{ formatTokenCount(text) }}</template>
        </a-table-column>
        <a-table-column title="费用" data-index="total_cost" key="total_cost">
          <template #default="{ text }">¥{{ Number(text).toFixed(6) }}</template>
        </a-table-column>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, reactive, computed } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import { getTokenStats, getTokenSummary, getCostReport } from '@/api/tokenApi'
import type { StatsResponse } from '@/types/api'
import { formatTokenCount } from '@/utils'

const query = reactive<{ dimension_type: string; granularity: 'daily' | 'hourly' }>({ dimension_type: 'model', granularity: 'daily' })
const dateRange = ref<[dayjs.Dayjs, dayjs.Dayjs]>([dayjs().subtract(6, 'day'), dayjs()])
const stats = ref<StatsResponse>({ dimension_type: 'model', points: [], total_tokens: 0, total_cost: 0 })
const dimensionItems = ref<any[]>([])
const chartRef = ref<HTMLDivElement>()

const totalRequests = computed(() => stats.value.points.reduce((sum, p) => sum + p.request_count, 0))

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
  // 组件销毁时清理旧实例，避免重复初始化
  chartInstance?.dispose()
  chartInstance = echarts.init(chartRef.value)
  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['输入 Token', '输出 Token'] },
    grid: { left: 50, right: 20, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: stats.value.points.map((p) => p.date) },
    yAxis: { type: 'value', name: 'Token' },
    series: [
      {
        name: '输入 Token',
        type: 'bar',
        stack: 'total',
        data: stats.value.points.map((p) => p.prompt_tokens),
        itemStyle: { color: '#1677ff' }
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

onMounted(loadStats)
</script>
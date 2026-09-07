<template>
  <div class="page-container">
    <!-- 统计卡片 -->
    <a-row :gutter="[16, 16]">
      <a-col :xs="12" :sm="12" :lg="6" v-for="card in statCards" :key="card.label">
        <StatCard
          :label="card.label"
          :value="card.value"
          :icon="card.icon"
          :color="card.color"
          :suffix="card.suffix"
          :formatter="card.formatter"
        />
      </a-col>
    </a-row>

    <!-- 趋势 + 模型状态 -->
    <a-row :gutter="[16, 16]" style="margin-top: 16px">
      <a-col :xs="24" :lg="15">
        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-title">Token 用量趋势</span>
            <a-radio-group v-model:value="trendDays" size="small" @change="renderChart">
              <a-radio-button value="7">7 天</a-radio-button>
              <a-radio-button value="30">30 天</a-radio-button>
            </a-radio-group>
          </div>
          <div class="panel-body">
            <a-spin :spinning="chartLoading">
              <div ref="chartRef" style="height: 300px"></div>
            </a-spin>
          </div>
        </div>
      </a-col>
      <a-col :xs="24" :lg="9">
        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-title">模型运行状态</span>
            <a-tag color="blue">{{ onlineCount }}/{{ modelStatusList.length }} 在线</a-tag>
          </div>
          <div class="panel-body padless">
            <a-empty v-if="!modelStatusList.length" description="暂无模型，请先在模型管理中添加" style="padding: 24px" />
            <a-list v-else size="small" :data-source="modelStatusList" style="padding: 0 8px">
              <template #renderItem="{ item }">
                <a-list-item style="padding: 10px 12px">
                  <a-list-item-meta>
                    <template #title>
                      <span style="font-weight: 500">{{ item.name }}</span>
                      <a-tag style="margin-left: 8px">{{ item.provider }}</a-tag>
                    </template>
                    <template #description>v{{ item.version }} · QPS {{ item.qps_limit }}</template>
                  </a-list-item-meta>
                  <template #extra>
                    <StatusTag :status="item.status" />
                  </template>
                </a-list-item>
              </template>
            </a-list>
          </div>
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import * as echarts from 'echarts'
import { RobotOutlined, KeyOutlined, ThunderboltOutlined, ApiOutlined } from '@ant-design/icons-vue'
import StatCard from '@/components/common/StatCard.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { getModelList } from '@/api/modelApi'
import { getKeyList } from '@/api/keyApi'
import type { ModelItem, KeyItem } from '@/types/api'
import { getTokenStats } from '@/api/tokenApi'
import { formatTokenCount } from '@/utils'

const statCards = ref([
  { label: '已接入模型', value: 0, icon: RobotOutlined, color: '#1677ff', suffix: '个' },
  { label: '活跃 Key', value: 0, icon: KeyOutlined, color: '#52c41a', suffix: '个' },
  { label: '今日 Token', value: 0, icon: ThunderboltOutlined, color: '#faad14', formatter: (n: number) => formatTokenCount(n) },
  { label: '今日请求量', value: 0, icon: ApiOutlined, color: '#f5222d', suffix: '次' }
])

const modelStatusList = ref<ModelItem[]>([])
const chartLoading = ref(false)
const chartRef = ref<HTMLDivElement>()
const trendDays = ref<number>(7)

const onlineCount = computed(() => modelStatusList.value.filter((m) => m.status === 'online').length)

async function loadDashboard() {
  try {
    const [models, keys] = await Promise.all([
      getModelList(),
      getKeyList({ page: 1, size: 999 })
    ])
    modelStatusList.value = models
    statCards.value[0].value = models.length
    statCards.value[1].value = keys.filter((k: KeyItem) => k.status === 'active').length
  } catch {
    /* 后台接口暂不可用时不阻塞页面 */
  }
}

async function renderChart() {
  if (!chartRef.value) return
  chartLoading.value = true
  try {
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - trendDays.value)

    const fmt = (d: Date) => d.toISOString().slice(0, 10)
    const stats = await getTokenStats({
      dimension_type: 'model',
      start_date: fmt(startDate),
      end_date: fmt(endDate),
      granularity: 'daily'
    })

    chartInstance?.dispose()
    const chart = echarts.init(chartRef.value)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['总 Token'], top: 0 },
      grid: { left: 50, right: 16, top: 32, bottom: 8 },
      xAxis: { type: 'category', data: stats.points.map((p) => p.date) },
      yAxis: { type: 'value', name: 'Token' },
      series: [{
        name: '总 Token',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        data: stats.points.map((p) => p.total_tokens),
        lineStyle: { width: 3, color: '#1890ff' },
        itemStyle: { color: '#1890ff' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(24,144,255,0.3)' },
            { offset: 1, color: 'rgba(24,144,255,0)' }
          ])
        }
      }]
    })
    chartInstance = chart
    resizeHandler = () => chart.resize()
    window.addEventListener('resize', resizeHandler)
  } finally {
    chartLoading.value = false
  }
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

onMounted(() => {
  loadDashboard()
  renderChart()
})
</script>

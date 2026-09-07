<template>
  <div class="page-container">
    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :sm="12" :lg="6" v-for="card in statCards" :key="card.title">
        <a-card>
          <a-statistic :title="card.title" :value="card.value" :suffix="card.suffix" :precision="card.precision">
            <template #prefix>
              <component :is="card.icon" :style="{ color: card.color, fontSize: '24px', marginRight: '8px' }" />
            </template>
          </a-statistic>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[16, 16]" style="margin-top: 16px">
      <a-col :xs="24" :lg="14">
        <a-card title="Token 用量趋势" :loading="chartLoading">
          <div ref="chartRef" style="height: 320px"></div>
        </a-card>
      </a-col>
      <a-col :xs="24" :lg="10">
        <a-card title="模型运行状态">
          <a-list size="small">
            <a-list-item v-for="model in modelStatusList" :key="model.id">
              <a-list-item-meta>
                <template #title>
                  <span>
                    <span class="status-dot" :class="`status-${model.status}`"></span>
                    {{ model.name }}
                  </span>
                </template>
                <template #description>
                  {{ model.provider }} · v{{ model.version }}
                </template>
              </a-list-item-meta>
              <template #extra>
                <a-tag :color="statusColor(model.status)">{{ statusText(model.status) }}</a-tag>
              </template>
            </a-list-item>
          </a-list>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { RobotOutlined, KeyOutlined, ThunderboltOutlined, ApiOutlined } from '@ant-design/icons-vue'
import { getModelList } from '@/api/modelApi'
import { getKeyList } from '@/api/keyApi'
import type { ModelItem, KeyItem } from '@/types/api'
import { getTokenStats } from '@/api/tokenApi'

const statCards = ref([
  { title: '已接入模型', value: 0, icon: RobotOutlined, color: '#1677ff', suffix: '个', precision: 0 },
  { title: '活跃 Key', value: 0, icon: KeyOutlined, color: '#52c41a', suffix: '个', precision: 0 },
  { title: '今日 Token', value: 0, icon: ThunderboltOutlined, color: '#faad14', suffix: '', precision: 0 },
  { title: '今日请求量', value: 0, icon: ApiOutlined, color: '#f5222d', suffix: '次', precision: 0 }
])

const modelStatusList = ref<ModelItem[]>([])
const chartLoading = ref(false)
const chartRef = ref<HTMLDivElement>()

const statusMap: Record<string, { text: string; color: string }> = {
  online: { text: '在线', color: 'success' },
  offline: { text: '离线', color: 'error' },
  high_latency: { text: '高延迟', color: 'warning' },
  pending: { text: '待配置', color: 'default' }
}

function statusColor(status: string) {
  return statusMap[status]?.color || 'default'
}
function statusText(status: string) {
  return statusMap[status]?.text || status
}

async function loadDashboard() {
  const [models, keys] = await Promise.all([
    getModelList(),
    getKeyList({ page: 1, size: 999 })
  ])

  modelStatusList.value = models
  statCards.value[0].value = models.length
  statCards.value[1].value = keys.filter((k: KeyItem) => k.status === 'active').length
}

async function renderChart() {
  if (!chartRef.value) return
  chartLoading.value = true
  try {
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - 7)

    const formatDate = (d: Date) => d.toISOString().slice(0, 10)
    const stats = await getTokenStats({
      dimension_type: 'model',
      start_date: formatDate(startDate),
      end_date: formatDate(endDate)
    })

    // 组件销毁时清理旧实例，避免重复初始化
    chartInstance?.dispose()
    const chart = echarts.init(chartRef.value)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['总 Token'] },
      grid: { left: 40, right: 20, top: 40, bottom: 40 },
      xAxis: { type: 'category', data: stats.points.map((p) => p.date) },
      yAxis: { type: 'value', name: 'Token' },
      series: [{
        name: '总 Token',
        type: 'bar',
        data: stats.points.map((p) => p.total_tokens),
        itemStyle: { color: '#1677ff' }
      }]
    })
    // 保存引用以便组件销毁时清理，避免重复注册监听
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

<style scoped>
.page-container {
  padding: 0;
}
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
  vertical-align: middle;
}
.status-dot.status-online {
  background-color: #52c41a;
}
.status-dot.status-offline {
  background-color: #ff4d4f;
}
.status-dot.status-high_latency {
  background-color: #faad14;
}
.status-dot.status-pending {
  background-color: #d9d9d9;
}
</style>
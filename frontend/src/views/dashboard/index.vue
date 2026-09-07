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
              <a-radio-button :value="7">7 天</a-radio-button>
              <a-radio-button :value="30">30 天</a-radio-button>
            </a-radio-group>
          </div>
          <div class="panel-body padless">
            <div class="chart-stage">
              <a-spin :spinning="chartLoading">
                <a-empty
                  v-if="chartEmpty"
                  :description="chartError ? `趋势图加载失败：${chartError}` : '所选时间范围内暂无 Token 用量数据（可切换 7/30 天）'"
                  style="padding: 80px 0"
                />
                <div v-show="!chartEmpty" ref="chartRef" style="height: 320px; width: 100%"></div>
              </a-spin>
            </div>
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
const chartEmpty = ref(false)
const chartError = ref('')
const trendDays = ref<number>(7)

const onlineCount = computed(() => modelStatusList.value.filter((m) => m.status === 'online').length)

async function loadDashboard() {
  try {
    const fmtLocal = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    const today = new Date()

    const [models, keys, todayStats] = await Promise.all([
      getModelList(),
      getKeyList({ page: 1, size: 999 }),
      // 今日 Token/请求量：按"今天"窗口查（聚合表 daily 粒度）
      getTokenStats({
        dimension_type: 'model',
        start_date: fmtLocal(today),
        end_date: fmtLocal(today),
        granularity: 'daily'
      }).catch(() => null)
    ])

    modelStatusList.value = models
    statCards.value[0].value = models.length
    statCards.value[1].value = keys.filter((k: KeyItem) => k.status === 'active').length

    if (todayStats) {
      statCards.value[2].value = todayStats.total_tokens || 0
      statCards.value[3].value = todayStats.points.reduce((sum, p) => sum + (p.request_count || 0), 0)
    }
  } catch {
    /* 后台接口暂不可用时不阻塞页面 */
  }
}

async function renderChart() {
  const el = chartRef.value
  if (!el) return
  chartLoading.value = true
  try {
    // radio-group 返回字符串，统一转数字
    const days = Number(trendDays.value) || 7
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(endDate.getDate() - days)

    // 用本地时间拼接 YYYY-MM-DD，避免 toISOString(UTC) 跨日错位
    const fmtLocal = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

    const stats = await getTokenStats({
      dimension_type: 'model',
      start_date: fmtLocal(startDate),
      end_date: fmtLocal(endDate),
      granularity: 'daily'
    })

    chartInstance?.dispose()
    // 空数据：隐藏图表并提示
    if (!stats.points || stats.points.length === 0) {
      chartEmpty.value = true
      return
    }
    chartEmpty.value = false
    const chart = echarts.init(el)
    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255,255,255,0.95)',
        textStyle: { color: '#333' }
      },
      grid: { left: 10, right: 10, top: 24, bottom: 24, containLabel: true },
      xAxis: {
        type: 'category',
        data: stats.points.map((p) => p.date.slice(5)), // MM-DD
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.4)' } },
        axisLabel: { color: 'rgba(255,255,255,0.85)', fontSize: 12 },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        name: 'Token',
        nameTextStyle: { color: 'rgba(255,255,255,0.6)' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.18)', type: 'dashed' } },
        axisLabel: { color: 'rgba(255,255,255,0.85)' }
      },
      series: [{
        name: '总 Token',
        type: 'bar',
        barWidth: '45%',
        itemStyle: {
          color: 'rgba(255,255,255,0.32)',
          borderRadius: [6, 6, 0, 0]
        },
        emphasis: { itemStyle: { color: 'rgba(255,255,255,0.55)' } },
        data: stats.points.map((p, i) => ({
          value: p.total_tokens,
          itemStyle: i === stats.points.length - 1
            ? { color: 'rgba(255,255,255,0.85)', borderRadius: [6, 6, 0, 0] } // 最后一天高亮
            : undefined
        }))
      }]
    })
    chartInstance = chart
    resizeHandler = () => chart.resize()
    window.addEventListener('resize', resizeHandler)
  } catch (e) {
    // 请求失败：不静默，展示错误原因便于定位
    console.error('[Dashboard] 趋势图加载失败:', e)
    chartEmpty.value = true
    chartError.value = e instanceof Error ? e.message : String(e)
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
/* 趋势图舞台：对齐原型 chart-mock 紫蓝渐变 */
.chart-stage {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  margin: 16px;
  padding: 8px 16px 4px;
  min-height: 200px;
  color: #fff;
}
</style>

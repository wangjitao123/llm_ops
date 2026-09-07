<template>
  <div class="page-container">
    <div class="page-title-row">
      <h3>模型对比评估</h3>
      <p>多模型综合评分与选型推荐</p>
    </div>
    <div class="panel-card">
      <div class="table-toolbar">
        <div></div>
        <a-button type="primary" @click="openCreateModal">
          <template #icon><PlusOutlined /></template>
          新建对比评估
        </a-button>
      </div>

      <a-table :data-source="evals" :loading="loading" row-key="id" :pagination="false">
        <a-table-column title="评估名称" data-index="name" key="name" />
        <a-table-column title="参与模型" key="model_names">
          <template #default="{ record }">
            <a-space wrap>
              <a-tag v-for="id in record.model_ids" :key="id" color="blue">{{ getModelName(id) }}</a-tag>
            </a-space>
          </template>
        </a-table-column>
        <a-table-column title="状态" key="status" width="100">
          <template #default="{ record }">
            <StatusTag :status="record.status" />
          </template>
        </a-table-column>
      <a-table-column title="综合评分" key="overall" width="100">
        <template #default="{ record }">
          <span v-if="record.result?.overall_score">
            <span style="font-size: 18px; font-weight: 600; color: #1677ff">{{ record.result.overall_score }}</span>
          </span>
          <span v-else>-</span>
        </template>
      </a-table-column>
      <a-table-column title="推荐建议" key="recommendation" ellipsis>
        <template #default="{ record }">{{ record.recommendation || '-' }}</template>
      </a-table-column>
      <a-table-column title="创建时间" data-index="created_at" key="created_at" width="170" />
      <a-table-column title="操作" key="action" width="100">
        <template #default="{ record }">
          <a-button type="link" size="small" @click="viewResult(record)">查看结果</a-button>
        </template>
      </a-table-column>
    </a-table>
    </div>

    <a-modal v-model:open="createModalOpen" title="新建对比评估" :confirm-loading="creating" @ok="handleCreate">
      <a-form :model="form" layout="vertical">
        <a-form-item label="评估名称" required>
          <a-input v-model:value="form.name" placeholder="如：客服场景模型选型" />
        </a-form-item>
        <a-form-item label="选择参与模型" required>
          <a-select v-model:value="form.model_ids" mode="multiple" :options="modelOptions" placeholder="至少选择 2 个模型" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-drawer v-model:open="resultOpen" title="评估结果" width="620px">
      <template v-if="currentResult">
        <a-card title="综合评分" style="margin-bottom: 16px">
          <div style="text-align: center; padding: 16px">
            <span style="font-size: 48px; font-weight: 700; color: #1677ff">{{ currentResult.result?.overall_score ?? '-' }}</span>
            <span style="font-size: 16px; color: #999; margin-left: 8px">/ 100</span>
          </div>
          <p v-if="currentResult.recommendation" style="text-align: center; color: #666">
            <a-tag color="gold">推荐</a-tag> {{ currentResult.recommendation }}
          </p>
        </a-card>

        <a-card title="模型评分明细">
          <div v-for="model in currentResult.result?.models || []" :key="model.model_id" style="margin-bottom: 24px">
            <h4>{{ model.model_name }}</h4>
            <a-row :gutter="[12, 12]">
              <a-col :span="8" v-for="(score, dim) in model.scores" :key="dim">
                <a-card size="small">
                  <div style="font-size: 12px; color: #999">{{ dimensionText(dim) }}</div>
                  <div style="font-size: 20px; font-weight: 600">{{ score }}</div>
                </a-card>
              </a-col>
            </a-row>
            <div style="margin-top: 8px; text-align: right">
              总分: <b style="color: #1677ff">{{ model.total_score }}</b>
            </div>
          </div>
        </a-card>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { message } from 'ant-design-vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { getCompareList, createCompare, getCompareDetail } from '@/api/compareApi'
import type { CompareItem } from '@/api/compareApi'
import { getModelList } from '@/api/modelApi'
import type { ModelItem } from '@/types/api'
import { formatTime } from '@/utils'

const evals = ref<CompareItem[]>([])
const models = ref<ModelItem[]>([])
const loading = ref(false)
const creating = ref(false)
const createModalOpen = ref(false)
const resultOpen = ref(false)
const currentResult = ref<CompareItem | null>(null)

const form = reactive({ name: '', model_ids: [] as number[] })

const modelOptions = computed(() => models.value.map((m) => ({ label: `${m.name} (${m.provider})`, value: m.id })))

const dimensionMap: Record<string, string> = {
  quality: '生成质量', latency: '响应延迟', cost: '调用成本',
  context: '上下文', stability: '稳定性', throughput: '吞吐量', ease_of_use: '易用性'
}
function dimensionText(d: string) { return dimensionMap[d] || d }

function getModelName(id: number) { return models.value.find((m) => m.id === id)?.name || `#${id}` }

async function loadEvals() {
  loading.value = true
  try {
    const list = (await getCompareList()) as CompareItem[]
    evals.value = list.map((e) => ({ ...e, created_at: formatTime(e.created_at) }))
  } finally { loading.value = false }
}

async function loadModels() {
  models.value = (await getModelList()) as ModelItem[]
}

function openCreateModal() {
  Object.assign(form, { name: '', model_ids: [] })
  createModalOpen.value = true
}

async function handleCreate() {
  if (!form.name || form.model_ids.length < 2) {
    message.warning('请填写评估名称并至少选择 2 个模型')
    return
  }
  creating.value = true
  try {
    await createCompare({ name: form.name, model_ids: form.model_ids })
    message.success('评估任务已创建')
    createModalOpen.value = false
    loadEvals()
  } catch { message.error('创建失败') } finally { creating.value = false }
}

async function viewResult(record: CompareItem) {
  try {
    const detail = (await getCompareDetail(record.id)) as CompareItem
    currentResult.value = detail
    resultOpen.value = true
  } catch { message.error('加载结果失败') }
}

onMounted(() => { loadEvals(); loadModels() })
</script>
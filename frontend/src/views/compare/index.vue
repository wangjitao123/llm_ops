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
            <a-tag v-if="record.status === 'completed'" color="green">已完成</a-tag>
            <a-tag v-else-if="record.status === 'running'" color="orange">
              <a-spin size="small" /> 评测中
            </a-tag>
            <a-tag v-else-if="record.status === 'failed'" color="red">失败</a-tag>
            <a-tag v-else color="default">待配置</a-tag>
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
        <a-table-column title="操作" key="action" width="180">
          <template #default="{ record }">
            <a-space>
              <a-button type="link" size="small" @click="handleRunEval(record)" :disabled="record.status === 'running' || record.status === 'completed'" :loading="runningId === record.id">
                {{ record.status === 'completed' ? '已评测' : record.status === 'running' ? '评测中' : '开始评估' }}
              </a-button>
              <a-button type="link" size="small" @click="viewResult(record)">{{ record.status === 'completed' ? '查看结果' : '详情' }}</a-button>
            </a-space>
          </template>
        </a-table-column>
      </a-table>
    </div>

    <a-modal v-model:open="createModalOpen" title="新建对比评估" :confirm-loading="creating" @ok="handleCreate" width="640px">
      <a-form :model="form" layout="vertical">
        <a-form-item label="评估名称" required>
          <a-input v-model:value="form.name" placeholder="如：客服场景模型选型" />
        </a-form-item>
        <a-form-item label="选择参与模型" required>
          <a-select v-model:value="form.model_ids" mode="multiple" :options="modelOptions" placeholder="至少选择 2 个模型" />
        </a-form-item>
        <a-form-item label="测试 Prompt（选填，每行一条完整消息，格式见说明）">
          <a-textarea v-model:value="form.promptsText" :rows="6" placeholder="你好，我想查询一下我的订单到了哪里&#10;我想退货退款，怎么操作&#10;你们的营业时间是几点到几点" />
          <div style="font-size: 12px; color: #999; margin-top: 4px">
            每天一行，发送时将自动包装为 <code>{"role": "user", "content": "你的问题"}</code>。不填则使用默认 5 条通用测试题。
          </div>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-drawer v-model:open="resultOpen" title="评估结果" width="640px" :after-open-change="onDrawerOpen">
      <template v-if="currentResult">
        <a-card title="综合评分" style="margin-bottom: 16px">
          <div style="text-align: center; padding: 16px">
            <span style="font-size: 48px; font-weight: 700; color: #1677ff">{{ currentResult.result?.overall_score ?? '-' }}</span>
            <span style="font-size: 16px; color: #999; margin-left: 8px">/ 100</span>
          </div>
          <p v-if="currentResult.recommendation" style="text-align: center; color: #666">
            <a-tag color="gold">推荐</a-tag> {{ currentResult.recommendation }}
          </p>
          <div v-if="currentResult.result?.errors" style="margin-top: 8px">
            <a-alert v-for="err in currentResult.result.errors" :key="err.model_id" type="error" :message="`模型 #${err.model_id}: ${err.error}`" show-icon style="margin-bottom: 4px" />
          </div>
        </a-card>

        <a-card title="模型评分明细">
          <div v-for="model in currentResult.result?.models || []" :key="model.model_id" style="margin-bottom: 24px">
            <a-row justify="space-between" align="middle">
              <h4 style="margin: 0">{{ model.model_name }}</h4>
              <a-tag v-if="model.error" color="red">{{ model.error }}</a-tag>
              <a-button v-else type="link" size="small" @click="editModelScore(model)">补充人工分</a-button>
            </a-row>
            <div v-if="model.scores_need_human && model.scores_need_human.length" style="margin: 4px 0 8px">
              <a-tag v-for="d in model.scores_need_human" :key="d" color="orange">待人工评测</a-tag>
            </div>
            <a-row :gutter="[12, 12]" style="margin-top: 8px">
              <a-col :span="8" v-for="(score, dim) in model.scores" :key="dim">
                <a-card size="small" :class="{ 'dim-need-human': model.scores_need_human?.includes(dim) }">
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

        <!-- 人工评分编辑 -->
        <a-modal v-model:open="scoreEditOpen" :title="`人工评分 — ${editModelName}`" @ok="saveEditScore" ok-text="保存" width="400px">
          <a-form :model="editForm" layout="vertical">
            <a-form-item label="生成质量 (0-100)">
              <a-input-number v-model:value="editForm.quality" :min="0" :max="100" style="width: 100%" />
            </a-form-item>
            <a-form-item label="易用性 (0-100)">
              <a-input-number v-model:value="editForm.ease_of_use" :min="0" :max="100" style="width: 100%" />
            </a-form-item>
          </a-form>
        </a-modal>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import {
  getCompareList, createCompare, getCompareDetail, runEval, updateEvalResult
} from '@/api/compareApi'
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
const runningId = ref<number | null>(null)

const form = reactive({
  name: '',
  model_ids: [] as number[],
  promptsText: '',
})

// 人工评分编辑
const scoreEditOpen = ref(false)
const editModelId = ref<number | null>(null)
const editModelName = ref('')
const editForm = reactive({ quality: 0, ease_of_use: 0 })

const modelOptions = computed(() => models.value.map((m) => ({ label: `${m.name} (${m.provider})`, value: m.id })))

const dimensionMap: Record<string, string> = {
  quality: '生成质量', latency: '响应延迟', cost: '调用成本',
  context: '上下文', stability: '稳定性', throughput: '吞吐量', ease_of_use: '易用性',
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
  Object.assign(form, { name: '', model_ids: [], promptsText: '' })
  createModalOpen.value = true
}

function parsePrompts(text: string): Array<Array<{ role: string; content: string }>> | undefined {
  const lines = text.split('\n').map((s) => s.trim()).filter(Boolean)
  if (!lines.length) return undefined
  return lines.map((line) => [{ role: 'user', content: line }])
}

async function handleCreate() {
  if (!form.name || form.model_ids.length < 2) {
    message.warning('请填写评估名称并至少选择 2 个模型')
    return
  }
  creating.value = true
  try {
    await createCompare({
      name: form.name,
      model_ids: form.model_ids,
      test_prompts: parsePrompts(form.promptsText),
    })
    message.success('评估任务已创建')
    createModalOpen.value = false
    loadEvals()
  } catch { message.error('创建失败') } finally { creating.value = false }
}

async function handleRunEval(record: CompareItem) {
  if (record.status === 'running' || record.status === 'completed') return
  runningId.value = record.id
  try {
    await runEval(record.id)
    message.success('评测完成')
    loadEvals()
    // 自动打开结果
    const detail = (await getCompareDetail(record.id)) as CompareItem
    currentResult.value = detail
    resultOpen.value = true
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '评测失败')
    loadEvals()
  } finally {
    runningId.value = null
  }
}

async function viewResult(record: CompareItem) {
  try {
    const detail = (await getCompareDetail(record.id)) as CompareItem
    currentResult.value = detail
    resultOpen.value = true
  } catch { message.error('加载结果失败') }
}

function onDrawerOpen(open: boolean) {
  if (open && currentResult.value) {
    loadEvals()
  }
}

function editModelScore(model: any) {
  editModelId.value = model.model_id
  editModelName.value = model.model_name
  editForm.quality = model.scores?.quality ?? 0
  editForm.ease_of_use = model.scores?.ease_of_use ?? 0
  scoreEditOpen.value = true
}

async function saveEditScore() {
  if (!currentResult.value || editModelId.value === null) return
  try {
    await updateEvalResult(currentResult.value.id, {
      models: [{
        model_id: editModelId.value,
        scores: { quality: editForm.quality, ease_of_use: editForm.ease_of_use },
      }],
    })
    message.success('评分已保存')
    scoreEditOpen.value = false
    // 刷新详情
    const detail = (await getCompareDetail(currentResult.value.id)) as CompareItem
    currentResult.value = detail
  } catch { message.error('保存失败') }
}

onMounted(() => { loadEvals(); loadModels() })
</script>

<style scoped>
.dim-need-human {
  opacity: 0.6;
}
</style>
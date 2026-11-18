<template>
  <div class="page-container">
    <div class="panel-card">
      <div class="table-toolbar">
        <div class="toolbar-filters">
          <a-select v-model:value="query.provider" placeholder="提供商" allow-clear style="width: 140px">
            <a-select-option v-for="p in providers" :key="p" :value="p">{{ p }}</a-select-option>
          </a-select>
          <a-select v-model:value="query.status" placeholder="状态" allow-clear style="width: 120px">
            <a-select-option value="online">在线</a-select-option>
            <a-select-option value="offline">离线</a-select-option>
            <a-select-option value="high_latency">高延迟</a-select-option>
          </a-select>
          <a-button type="primary" @click="loadModels">
            <template #icon><SearchOutlined /></template>
            查询
          </a-button>
        </div>
        <div class="toolbar-actions">
          <a-button type="primary" @click="openCreateModal">
            <template #icon><PlusOutlined /></template>
            添加模型
          </a-button>
        </div>
      </div>

      <a-table :data-source="models" :loading="loading" row-key="id" :pagination="false">
        <a-table-column title="模型名称" data-index="name" key="name">
          <template #default="{ record }">
            <a-space>
              <a-avatar size="small" style="background: #e6f7ff; color: #1890ff; font-size: 13px">
                {{ (record.provider || '?')[0].toUpperCase() }}
              </a-avatar>
              <span style="font-weight: 500">{{ record.name }}</span>
              <a-tag v-if="unpricedIds.includes(record.id)" color="orange">未计费</a-tag>
            </a-space>
          </template>
        </a-table-column>
        <a-table-column title="提供商" data-index="provider" key="provider">
          <template #default="{ text }">
            <a-tag color="blue">{{ text }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="版本" data-index="version" key="version" width="80" />
        <a-table-column title="QPS 限制" data-index="qps_limit" key="qps_limit" width="100" />
        <a-table-column title="状态" key="status" width="110">
          <template #default="{ record }">
            <StatusTag :status="record.status" />
          </template>
        </a-table-column>
        <a-table-column title="API 地址" data-index="api_base_url" key="api_base_url" ellipsis />
        <a-table-column title="操作" key="action" width="320">
          <template #default="{ record }">
            <a-space>
              <a-button type="link" size="small" @click="openEditModal(record)">编辑</a-button>
              <a-button type="link" size="small" @click="toggleStatus(record)">
                {{ record.status === 'online' ? '停用' : '启用' }}
              </a-button>
              <a-button type="link" size="small" @click="showVersions(record)">版本</a-button>
              <a-button type="link" size="small" @click="openPricingModal(record)">计费</a-button>
              <a-popconfirm title="确定删除该模型？" ok-text="删除" cancel-text="取消" @confirm="handleDelete(record)">
                <a-button type="link" danger size="small">删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </a-table-column>
      </a-table>
    </div>

    <a-modal v-model:open="modalOpen" :title="editing ? '编辑模型' : '添加模型'" :confirm-loading="saving" @ok="handleSubmit">
      <a-form ref="formRef" :model="form" :rules="rules" layout="vertical">
        <a-form-item label="模型名称" name="name">
          <a-input v-model:value="form.name" placeholder="如：DeepSeek-V3" />
        </a-form-item>
        <a-form-item label="提供商" name="provider">
          <a-select v-model:value="form.provider" placeholder="选择提供商">
            <a-select-option v-for="p in providers" :key="p" :value="p">{{ p }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="API 地址" name="api_base_url">
          <a-input v-model:value="form.api_base_url" placeholder="https://api.example.com/v1" />
        </a-form-item>
        <a-form-item v-if="!editing" label="API Key" name="api_key">
          <a-input-password v-model:value="form.api_key" placeholder="模型厂商的 API Key" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="QPS 上限" name="qps_limit">
              <a-input-number v-model:value="form.qps_limit" :min="1" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="超时(ms)" name="timeout_ms">
              <a-input-number v-model:value="form.timeout_ms" :min="1000" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="权重" name="weight">
              <a-input-number v-model:value="form.weight" :min="1" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述" name="description">
          <a-textarea v-model:value="form.description" :rows="2" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="versionModalOpen" title="模型版本历史" :footer="null" width="640px">
      <a-table :data-source="versions" row-key="id" :pagination="false" size="small">
        <a-table-column title="版本号" data-index="version" key="version" width="100" />
        <a-table-column title="是否当前" key="is_current" width="100">
          <template #default="{ record }">
            <a-tag v-if="record.is_current" color="green">当前版本</a-tag>
            <span v-else>-</span>
          </template>
        </a-table-column>
        <a-table-column title="变更说明" data-index="change_log" key="change_log" />
        <a-table-column title="创建时间" data-index="created_at" key="created_at" width="180" />
      </a-table>
    </a-modal>

    <a-modal
      v-model:open="pricingModalOpen"
      :title="`计费单价 - ${pricingModelName}`"
      :confirm-loading="pricingSaving"
      @ok="handleSavePricing"
      width="520px"
    >
      <a-alert
        type="info"
        show-icon
        style="margin-bottom: 12px"
        message="单价按「元 / 千 token」填写；未配置的模型按 0 元计费。改价只影响之后聚合出的账单，不追溯改写历史。"
      />
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="输入单价（元/千 token）">
              <a-input-number
                v-model:value="pricingForm.input_price_per_1k"
                :min="0"
                :precision="6"
                :step="0.001"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="输出单价（元/千 token）">
              <a-input-number
                v-model:value="pricingForm.output_price_per_1k"
                :min="0"
                :precision="6"
                :step="0.001"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="备注">
          <a-input v-model:value="pricingForm.remark" placeholder="如：官方价 / 内部结算价" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { getModelList, createModel, updateModel, deleteModel, updateModelStatus, getModelVersions } from '@/api/modelApi'
import { getPricingList, savePricing } from '@/api/pricingApi'
import type { ModelItem } from '@/types/api'
import StatusTag from '@/components/common/StatusTag.vue'
import { formatTime } from '@/utils'

const models = ref<ModelItem[]>([])
const loading = ref(false)
const modalOpen = ref(false)
const saving = ref(false)
const editing = ref(false)
const versions = ref<any[]>([])
const versionModalOpen = ref(false)

// 计费单价
const pricingModalOpen = ref(false)
const pricingSaving = ref(false)
const pricingModelId = ref<number>()
const pricingModelName = ref('')
const pricingForm = reactive({ input_price_per_1k: 0, output_price_per_1k: 0, remark: '' })
const pricingItems = ref<any[]>([])
const unpricedIds = ref<number[]>([])

const providers = ['deepseek', 'openai', 'aliyun', 'baidu', 'anthropic', 'google']

const query = reactive({ provider: undefined as string | undefined, status: undefined as string | undefined })
const form = reactive({
  id: undefined as number | undefined,
  name: '',
  provider: '',
  api_base_url: '',
  api_key: '',
  qps_limit: 100,
  timeout_ms: 60000,
  weight: 1,
  description: ''
})

const rules = {
  name: [{ required: true, message: '请输入模型名称' }],
  provider: [{ required: true, message: '请选择提供商' }],
  api_base_url: [{ required: true, message: '请输入 API 地址' }],
  api_key: [{ required: true, message: '请输入 API Key', trigger: 'blur' }]
}

async function loadModels() {
  loading.value = true
  try {
    models.value = await getModelList(query)
  } finally {
    loading.value = false
  }
}

function openCreateModal() {
  editing.value = false
  Object.assign(form, { id: undefined, name: '', provider: '', api_base_url: '', api_key: '', qps_limit: 100, timeout_ms: 60000, weight: 1, description: '' })
  modalOpen.value = true
}

function openEditModal(record: ModelItem) {
  editing.value = true
  Object.assign(form, {
    id: record.id, name: record.name, provider: record.provider,
    api_base_url: record.api_base_url, api_key: '', qps_limit: record.qps_limit,
    timeout_ms: record.timeout_ms, weight: record.weight, description: record.description || ''
  })
  modalOpen.value = true
}

async function handleSubmit() {
  saving.value = true
  try {
    if (editing.value && form.id) {
      const { id, api_key, ...updateData } = form
      await updateModel(form.id, updateData)
      message.success('模型更新成功')
    } else {
      await createModel({ ...form })
      message.success('模型创建成功')
    }
    modalOpen.value = false
    loadModels()
  } catch (e) {
    message.error('操作失败')
  } finally {
    saving.value = false
  }
}

async function toggleStatus(record: ModelItem) {
  const newStatus = record.status === 'online' ? 'offline' : 'online'
  await updateModelStatus(record.id, newStatus)
  message.success(`模型已${newStatus === 'online' ? '启用' : '停用'}`)
  loadModels()
}

async function handleDelete(record: ModelItem) {
  await deleteModel(record.id)
  message.success('模型已删除')
  loadModels()
}

async function showVersions(record: ModelItem) {
  versions.value = (await getModelVersions(record.id)) as any[]
  versions.value = versions.value.map((v) => ({ ...v, created_at: formatTime(v.created_at) }))
  versionModalOpen.value = true
}

async function loadPricing() {
  const data = (await getPricingList()) as any
  pricingItems.value = data?.items || []
  unpricedIds.value = data?.unpriced_model_ids || []
}

function openPricingModal(record: ModelItem) {
  pricingModelId.value = record.id
  pricingModelName.value = record.name
  const existing = pricingItems.value.find((p) => p.model_id === record.id)
  Object.assign(pricingForm, {
    input_price_per_1k: existing?.input_price_per_1k ?? 0,
    output_price_per_1k: existing?.output_price_per_1k ?? 0,
    remark: existing?.remark || ''
  })
  pricingModalOpen.value = true
}

async function handleSavePricing() {
  if (!pricingModelId.value) return
  pricingSaving.value = true
  try {
    await savePricing(pricingModelId.value, { ...pricingForm })
    message.success('计费单价已保存')
    pricingModalOpen.value = false
    loadPricing()
  } finally {
    pricingSaving.value = false
  }
}

onMounted(() => {
  loadModels()
  loadPricing()
})
</script>

<style scoped>
.page-container {
  padding: 0;
}
.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
</style>
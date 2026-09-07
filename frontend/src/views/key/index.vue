<template>
  <div class="page-container">
    <div class="table-toolbar">
      <a-space>
        <a-select v-model:value="query.status" placeholder="状态" allow-clear style="width: 120px">
          <a-select-option value="active">启用</a-select-option>
          <a-select-option value="disabled">禁用</a-select-option>
          <a-select-option value="expired">过期</a-select-option>
        </a-select>
        <a-button type="primary" @click="loadKeys">
          <template #icon><SearchOutlined /></template>
          查询
        </a-button>
      </a-space>
      <a-space>
        <a-button @click="openAppModal">应用管理</a-button>
        <a-button type="primary" @click="openCreateModal">
          <template #icon><PlusOutlined /></template>
          新建 Key
        </a-button>
      </a-space>
    </div>

    <a-table :data-source="keys" :loading="loading" row-key="id" :pagination="false">
      <a-table-column title="Key 名称" data-index="name" key="name" />
      <a-table-column title="Key" key="key_prefix" width="140">
        <template #default="{ record }">
          <span>{{ record.key_prefix }}****</span>
        </template>
      </a-table-column>
      <a-table-column title="状态" key="status" width="90">
        <template #default="{ record }">
          <a-tag :color="keyStatusColor(record.status)">{{ keyStatusText(record.status) }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="QPS 限制" data-index="qps_limit" key="qps_limit" width="90">
        <template #default="{ text }">{{ text || '全局' }}</template>
      </a-table-column>
      <a-table-column title="Token 配额" key="token_quota" width="100">
        <template #default="{ record }">{{ record.token_quota ? formatTokenCount(record.token_quota) : '不限' }}</template>
      </a-table-column>
      <a-table-column title="过期时间" data-index="expires_at" key="expires_at" width="160">
        <template #default="{ text }">{{ text ? formatTime(text) : '永久' }}</template>
      </a-table-column>
      <a-table-column title="操作" key="action" width="220">
        <template #default="{ record }">
          <a-space>
            <a-button type="link" size="small" @click="openEditModal(record)">编辑</a-button>
            <a-button type="link" size="small" @click="toggleStatus(record)">
              {{ record.status === 'active' ? '禁用' : '启用' }}
            </a-button>
            <a-popconfirm title="确定回收该 Key？" @confirm="handleDelete(record)">
              <a-button type="link" danger size="small">回收</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:open="modalOpen" :title="editing ? '编辑 Key' : '新建 API Key'" :confirm-loading="saving" @ok="handleSubmit" width="600px">
      <a-form ref="formRef" :model="form" layout="vertical">
        <a-form-item label="Key 名称" name="name" :rules="[{ required: true, message: '请输入名称' }]">
          <a-input v-model:value="form.name" placeholder="如：订单服务 Key" />
        </a-form-item>
        <a-form-item label="所属应用">
          <a-select v-model:value="form.application_id" allow-clear placeholder="选择应用">
            <a-select-option v-for="app in applications" :key="app.id" :value="app.id">{{ app.name }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="可调用模型">
          <a-select v-model:value="form.model_ids" mode="multiple" placeholder="选择可访问的模型" :options="modelOptions" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="QPS 限制">
              <a-input-number v-model:value="form.qps_limit" :min="1" placeholder="默认" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="Token 配额">
              <a-input-number v-model:value="form.token_quota" :min="1" placeholder="不限" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="过期时间">
              <a-date-picker v-model:value="form.expires_at" style="width: 100%" show-time />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>

    <!-- 创建成功后显示完整 Key -->
    <a-modal v-model:open="keyResultModal" title="Key 创建成功" :footer="null" width="560px">
      <a-alert type="warning" message="请立即复制保存此 Key，关闭后将无法再次查看完整 Key！" show-icon style="margin-bottom: 16px" />
      <a-input-group compact>
        <a-input v-model:value="generatedKey" read-only style="width: calc(100% - 80px)" />
        <a-button type="primary" @click="copyKey">
          <template #icon><CopyOutlined /></template>
          复制
        </a-button>
      </a-input-group>
    </a-modal>

    <!-- 应用管理 -->
    <a-modal v-model:open="appModalOpen" title="应用管理" :footer="null" width="560px">
      <a-space style="margin-bottom: 16px">
        <a-input v-model:value="newAppName" placeholder="应用名称" style="width: 200px" />
        <a-button type="primary" @click="addApplication">
          <template #icon><PlusOutlined /></template>
          添加
        </a-button>
      </a-space>
      <a-list size="small">
        <a-list-item v-for="app in applications" :key="app.id">
          <a-list-item-meta :title="app.name" :description="app.description" />
        </a-list-item>
      </a-list>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { PlusOutlined, SearchOutlined, CopyOutlined } from '@ant-design/icons-vue'
import { getKeyList, createKey, updateKey, deleteKey, getApplicationList, createApplication } from '@/api/keyApi'
import { getModelList } from '@/api/modelApi'
import type { KeyItem, ApplicationItem, ModelItem } from '@/types/api'
import { formatTime, formatTokenCount } from '@/utils'

const keys = ref<KeyItem[]>([])
const applications = ref<ApplicationItem[]>([])
const models = ref<ModelItem[]>([])
const loading = ref(false)
const modalOpen = ref(false)
const saving = ref(false)
const editing = ref(false)
const keyResultModal = ref(false)
const generatedKey = ref('')
const appModalOpen = ref(false)
const newAppName = ref('')

const query = reactive({ status: undefined as string | undefined })

const form = reactive({
  id: undefined as number | undefined,
  name: '',
  application_id: undefined as number | undefined,
  model_ids: [] as number[],
  qps_limit: undefined as number | undefined,
  token_quota: undefined as number | undefined,
  expires_at: undefined as any
})

const modelOptions = computed(() => models.value.map((m) => ({ label: `${m.name} (${m.provider})`, value: m.id })))

const keyStatusMap: Record<string, { text: string; color: string }> = {
  active: { text: '启用', color: 'success' },
  disabled: { text: '禁用', color: 'default' },
  expired: { text: '过期', color: 'warning' },
  revoked: { text: '已回收', color: 'error' }
}

function keyStatusColor(status: string) { return keyStatusMap[status]?.color || 'default' }
function keyStatusText(status: string) { return keyStatusMap[status]?.text || status }

async function loadKeys() {
  loading.value = true
  try {
    keys.value = (await getKeyList(query)) as KeyItem[]
  } finally {
    loading.value = false
  }
}

async function loadApplications() {
  applications.value = (await getApplicationList()) as ApplicationItem[]
}

async function loadModels() {
  models.value = (await getModelList()) as ModelItem[]
}

function openCreateModal() {
  editing.value = false
  Object.assign(form, { id: undefined, name: '', application_id: undefined, model_ids: [], qps_limit: undefined, token_quota: undefined, expires_at: undefined })
  modalOpen.value = true
}

function openEditModal(record: KeyItem) {
  editing.value = true
  Object.assign(form, {
    id: record.id, name: record.name, application_id: record.application_id,
    model_ids: [], qps_limit: record.qps_limit, token_quota: record.token_quota,
    expires_at: record.expires_at ? dayjs(record.expires_at) : undefined
  })
  modalOpen.value = true
}

async function handleSubmit() {
  saving.value = true
  try {
    const payload: any = { ...form }
    if (payload.expires_at) {
      payload.expires_at = dayjs(payload.expires_at).toISOString()
    } else {
      delete payload.expires_at
    }
    if (payload.qps_limit === undefined) delete payload.qps_limit
    if (payload.token_quota === undefined) delete payload.token_quota
    delete payload.id

    if (editing.value && form.id) {
      await updateKey(form.id, payload)
      message.success('Key 更新成功')
    } else {
      const result = (await createKey(payload)) as any
      generatedKey.value = result?.key_full || ''
      keyResultModal.value = true
      message.success('Key 创建成功')
    }
    modalOpen.value = false
    loadKeys()
  } catch (e) {
    message.error('操作失败')
  } finally {
    saving.value = false
  }
}

async function toggleStatus(record: KeyItem) {
  const newStatus = record.status === 'active' ? 'disabled' : 'active'
  await updateKey(record.id, { status: newStatus })
  message.success('状态已更新')
  loadKeys()
}

async function handleDelete(record: KeyItem) {
  await deleteKey(record.id)
  message.success('Key 已回收')
  loadKeys()
}

async function copyKey() {
  try {
    await navigator.clipboard.writeText(generatedKey.value)
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败，请手动复制')
  }
}

function openAppModal() {
  loadApplications()
  appModalOpen.value = true
}

async function addApplication() {
  if (!newAppName.value) {
    message.warning('请输入应用名称')
    return
  }
  await createApplication({ name: newAppName.value })
  newAppName.value = ''
  message.success('应用添加成功')
  loadApplications()
}

onMounted(() => {
  loadKeys()
  loadModels()
  loadApplications()
})
</script>
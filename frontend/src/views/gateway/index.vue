<template>
  <div class="page-container">
    <div class="table-toolbar">
      <a-space>
        <a-select v-model:value="query.status" placeholder="状态" allow-clear style="width: 120px">
          <a-select-option value="enabled">启用</a-select-option>
          <a-select-option value="disabled">停用</a-select-option>
        </a-select>
        <a-button type="primary" @click="loadRoutes">查询</a-button>
      </a-space>
      <a-button type="primary" @click="openCreateModal">
        <template #icon><PlusOutlined /></template>
        新建路由
      </a-button>
    </div>

    <a-table :data-source="routes" :loading="loading" row-key="id" :pagination="false">
      <a-table-column title="规则名称" data-index="name" key="name" width="150" />
      <a-table-column title="路径匹配" key="path" width="200">
        <template #default="{ record }">
          <code>{{ record.match_type }}: {{ record.path_pattern }}</code>
        </template>
      </a-table-column>
      <a-table-column title="路由策略" key="strategy" width="100">
        <template #default="{ text }">{{ strategyText(text) }}</template>
      </a-table-column>
      <a-table-column title="目标模型" key="targets">
        <template #default="{ record }">
          <a-space wrap>
            <a-tag v-for="t in getModelTargets(record)" :key="t.model_id" color="blue">
              {{ getModelName(t.model_id) }} ({{ record.strategy === 'weighted' ? `权重 ${t.weight}` : `优先级 ${t.priority || 0}` }})
            </a-tag>
            <span v-if="!record.model_targets?.length">-</span>
          </a-space>
        </template>
      </a-table-column>
      <a-table-column title="状态" key="status" width="90">
        <template #default="{ record }">
          <a-tag :color="record.status === 'enabled' ? 'success' : 'default'">
            {{ record.status === 'enabled' ? '启用' : '停用' }}
          </a-tag>
        </template>
      </a-table-column>
      <a-table-column title="操作" key="action" width="240">
        <template #default="{ record }">
          <a-space>
            <a-button type="link" size="small" @click="openEditModal(record)">编辑</a-button>
            <a-button type="link" size="small" @click="toggleStatus(record)">
              {{ record.status === 'enabled' ? '停用' : '启用' }}
            </a-button>
            <a-button type="link" size="small" @click="handleSync(record)">同步网关</a-button>
            <a-popconfirm title="确定删除该路由？" @confirm="handleDelete(record)">
              <a-button type="link" danger size="small">删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:open="modalOpen" :title="editing ? '编辑路由' : '新建路由'" :confirm-loading="saving" @ok="handleSubmit" width="700px">
      <a-form :model="form" layout="vertical">
        <a-form-item label="规则名称" required>
          <a-input v-model:value="form.name" placeholder="如：chat-completions 路由" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="16">
            <a-form-item label="路径匹配模式" required>
              <a-input v-model:value="form.path_pattern" placeholder="/v1/chat/completions" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="匹配方式" required>
              <a-select v-model:value="form.match_type">
                <a-select-option value="exact">精确匹配</a-select-option>
                <a-select-option value="prefix">前缀匹配</a-select-option>
                <a-select-option value="regex">正则匹配</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="路由策略" required>
              <a-select v-model:value="form.strategy">
                <a-select-option value="weighted">加权轮询</a-select-option>
                <a-select-option value="active_standby">主备切换</a-select-option>
                <a-select-option value="single">单点</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="优先级">
              <a-input-number v-model:value="form.priority" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="目标模型">
          <div v-for="(target, idx) in form.model_targets" :key="idx" style="display: flex; gap: 8px; margin-bottom: 8px">
            <a-select v-model:value="target.model_id" style="flex: 1" placeholder="选择模型" :options="modelOptions" />
            <a-input-number
              v-if="form.strategy === 'weighted'"
              v-model:value="target.weight"
              :min="1"
              placeholder="权重"
              style="width: 120px"
            />
            <a-input-number
              v-else
              v-model:value="target.priority"
              :min="0"
              placeholder="优先级"
              style="width: 120px"
            />
            <a-button danger @click="removeTarget(idx)"><DeleteOutlined /></a-button>
          </div>
          <a-button type="dashed" block @click="addTarget">
            <template #icon><PlusOutlined /></template>
            添加目标模型
          </a-button>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { getRouteList, createRoute, updateRoute, deleteRoute, syncRouteToHigress } from '@/api/gatewayApi'
import { getModelList } from '@/api/modelApi'
import type { RouteRuleItem, ModelItem } from '@/types/api'

const routes = ref<RouteRuleItem[]>([])
const models = ref<ModelItem[]>([])
const loading = ref(false)
const modalOpen = ref(false)
const saving = ref(false)
const editing = ref(false)

const query = reactive({ status: undefined as string | undefined })

const form = reactive({
  id: undefined as number | undefined,
  name: '',
  path_pattern: '',
  match_type: 'exact',
  strategy: 'weighted',
  priority: 0,
  model_targets: [] as Array<{ model_id?: number; weight?: number; priority?: number }>
})

const modelOptions = computed(() => models.value.map((m) => ({ label: `${m.name} (${m.provider})`, value: m.id })))

const strategyMap: Record<string, string> = {
  weighted: '加权轮询',
  active_standby: '主备切换',
  single: '单点'
}

function strategyText(s: string) { return strategyMap[s] || s }
function getModelName(id: number) { return models.value.find((m) => m.id === id)?.name || `#${id}` }
function getModelTargets(record: RouteRuleItem) { return record.model_targets || [] }

async function loadRoutes() {
  loading.value = true
  try {
    routes.value = (await getRouteList(query)) as RouteRuleItem[]
  } finally {
    loading.value = false
  }
}

async function loadModels() {
  models.value = (await getModelList()) as ModelItem[]
}

function openCreateModal() {
  editing.value = false
  Object.assign(form, { id: undefined, name: '', path_pattern: '', match_type: 'exact', strategy: 'weighted', priority: 0, model_targets: [] })
  modalOpen.value = true
}

function openEditModal(record: RouteRuleItem) {
  editing.value = true
  Object.assign(form, {
    id: record.id, name: record.name, path_pattern: record.path_pattern,
    match_type: record.match_type, strategy: record.strategy, priority: record.priority,
    model_targets: (record.model_targets || []).map((t) => ({ ...t }))
  })
  modalOpen.value = true
}

function addTarget() {
  form.model_targets.push({})
}

function removeTarget(idx: number) {
  form.model_targets.splice(idx, 1)
}

async function handleSubmit() {
  saving.value = true
  try {
    const payload: any = { ...form }
    delete payload.id
    if (editing.value && form.id) {
      await updateRoute(form.id, payload)
      message.success('路由更新成功')
    } else {
      await createRoute(payload)
      message.success('路由创建成功')
    }
    modalOpen.value = false
    loadRoutes()
  } catch (e) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function toggleStatus(record: RouteRuleItem) {
  const newStatus = record.status === 'enabled' ? 'disabled' : 'enabled'
  await updateRoute(record.id, { status: newStatus })
  message.success('状态已更新')
  loadRoutes()
}

async function handleSync(record: RouteRuleItem) {
  try {
    await syncRouteToHigress(record.id)
    message.success('已同步到 Higress 网关')
  } catch {
    message.error('同步失败')
  }
}

async function handleDelete(record: RouteRuleItem) {
  await deleteRoute(record.id)
  message.success('路由已删除')
  loadRoutes()
}

onMounted(() => {
  loadRoutes()
  loadModels()
})
</script>
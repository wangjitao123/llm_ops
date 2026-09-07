<template>
  <div class="page-container">
    <a-tabs v-model:activeKey="activeTab">
      <a-tab-pane key="tasks" tab="微调任务">
        <div class="table-toolbar">
          <a-space>
            <a-select v-model:value="taskQuery.status" placeholder="状态" allow-clear style="width: 130px">
              <a-select-option v-for="(text, val) in taskStatusMap" :key="val" :value="val">{{ text }}</a-select-option>
            </a-select>
            <a-button type="primary" @click="loadTasks">查询</a-button>
          </a-space>
          <a-button type="primary" @click="openCreateTaskModal">
            <template #icon><PlusOutlined /></template>
            创建微调任务
          </a-button>
        </div>

        <a-table :data-source="tasks" :loading="taskLoading" row-key="id" :pagination="false">
          <a-table-column title="任务名称" data-index="name" key="name" />
          <a-table-column title="基座模型" key="base_model_id" width="130">
            <template #default="{ record }">{{ getModelName(record.base_model_id) }}</template>
          </a-table-column>
          <a-table-column title="状态" key="status" width="100">
            <template #default="{ record }">
              <a-tag :color="taskStatusColor(record.status)">{{ taskStatusText(record.status) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="进度" key="progress" width="180">
            <template #default="{ record }">
              <a-progress :percent="record.progress" size="small" />
            </template>
          </a-table-column>
          <a-table-column title="Loss" data-index="loss_value" key="loss" width="100">
            <template #default="{ text }">{{ text ?? '-' }}</template>
          </a-table-column>
          <a-table-column title="创建人" data-index="created_by" key="created_by" width="100" />
          <a-table-column title="操作" key="action" width="180">
            <template #default="{ record }">
              <a-space>
                <a-button type="link" size="small" @click="viewTaskDetail(record)">详情</a-button>
                <a-popconfirm v-if="['pending', 'queued', 'running'].includes(record.status)" title="确定取消该任务？" @confirm="cancelTask(record)">
                  <a-button type="link" danger size="small">取消</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="datasets" tab="数据集">
        <div class="table-toolbar">
          <div></div>
          <a-button type="primary" @click="openDatasetModal">
            <template #icon><UploadOutlined /></template>
            上传数据集
          </a-button>
        </div>
        <a-table :data-source="datasets" :loading="datasetLoading" row-key="id" :pagination="false">
          <a-table-column title="数据集名称" data-index="name" key="name" />
          <a-table-column title="格式" data-index="format" key="format" width="80">
            <template #default="{ text }"><a-tag color="purple">{{ text }}</a-tag></template>
          </a-table-column>
          <a-table-column title="样本数" data-index="sample_count" key="samples" width="100" />
          <a-table-column title="文件大小" key="file_size" width="100">
            <template #default="{ record }">{{ formatFileSize(record.file_size) }}</template>
          </a-table-column>
          <a-table-column title="版本" data-index="version" key="version" width="80" />
          <a-table-column title="标注状态" key="annotation_status" width="110">
            <template #default="{ record }">
              <a-tag>{{ annotationStatusText(record.annotation_status) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="创建人" data-index="created_by" key="created_by" width="100" />
        </a-table>
      </a-tab-pane>
    </a-tabs>

    <!-- 创建任务 -->
    <a-modal v-model:open="taskModalOpen" title="创建微调任务" :confirm-loading="saving" @ok="handleCreateTask" width="620px">
      <a-form :model="taskForm" layout="vertical">
        <a-form-item label="任务名称" required>
          <a-input v-model:value="taskForm.name" placeholder="如：客服问答模型 v2 微调" />
        </a-form-item>
        <a-form-item label="基座模型" required>
          <a-select v-model:value="taskForm.base_model_id" :options="modelOptions" placeholder="选择基座模型" />
        </a-form-item>
        <a-form-item label="训练数据集" required>
          <a-select v-model:value="taskForm.dataset_id" :options="datasetOptions" placeholder="选择数据集" />
        </a-form-item>
        <a-divider style="margin: 12px 0">超参数</a-divider>
        <a-row :gutter="12">
          <a-col :span="8">
            <a-form-item label="Epochs"><a-input-number v-model:value="taskForm.hyper_params.epochs" :min="1" :max="20" style="width: 100%" /></a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="Learning Rate"><a-input-number v-model:value="taskForm.hyper_params.learning_rate" :min="0.00001" :max="0.01" :step="0.00001" style="width: 100%" /></a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="Batch Size"><a-input-number v-model:value="taskForm.hyper_params.batch_size" :min="1" :max="64" style="width: 100%" /></a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="LoRA Rank"><a-input-number v-model:value="taskForm.hyper_params.lora_rank" :min="1" :max="64" style="width: 100%" /></a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="LoRA Alpha"><a-input-number v-model:value="taskForm.hyper_params.lora_alpha" :min="1" :max="128" style="width: 100%" /></a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>

    <!-- 任务详情 -->
    <a-modal v-model:open="detailModalOpen" :footer="null" title="任务详情" width="700px">
      <a-descriptions bordered size="small" :column="2" v-if="currentTask">
        <a-descriptions-item label="任务名称">{{ currentTask.name }}</a-descriptions-item>
        <a-descriptions-item label="状态">{{ taskStatusText(currentTask.status) }}</a-descriptions-item>
        <a-descriptions-item label="基座模型">{{ getModelName(currentTask.base_model_id) }}</a-descriptions-item>
        <a-descriptions-item label="数据集 ID">{{ currentTask.dataset_id }}</a-descriptions-item>
        <a-descriptions-item label="进度">{{ currentTask.progress }}%</a-descriptions-item>
        <a-descriptions-item label="Loss">{{ currentTask.loss_value ?? '-' }}</a-descriptions-item>
        <a-descriptions-item label="开始时间">{{ currentTask.started_at || '-' }}</a-descriptions-item>
        <a-descriptions-item label="完成时间">{{ currentTask.finished_at || '-' }}</a-descriptions-item>
        <a-descriptions-item label="超参数" :span="2">
          <pre style="max-height: 200px; overflow: auto; margin: 0">{{ JSON.stringify(currentTask.hyper_params, null, 2) }}</pre>
        </a-descriptions-item>
        <a-descriptions-item v-if="currentTask.error_message" label="错误信息" :span="2">
          <span style="color: #f5222d">{{ currentTask.error_message }}</span>
        </a-descriptions-item>
      </a-descriptions>
    </a-modal>

    <!-- 上传数据集 -->
    <a-modal v-model:open="datasetModalOpen" title="上传数据集" :confirm-loading="datasetSaving" @ok="handleCreateDataset">
      <a-form :model="datasetForm" layout="vertical">
        <a-form-item label="数据集名称" required>
          <a-input v-model:value="datasetForm.name" placeholder="如：客服问答训练集" />
        </a-form-item>
        <a-form-item label="文件格式" required>
          <a-select v-model:value="datasetForm.format">
            <a-select-option value="jsonl">JSONL</a-select-option>
            <a-select-option value="csv">CSV</a-select-option>
            <a-select-option value="json">JSON</a-select-option>
            <a-select-option value="parquet">Parquet</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="datasetForm.description" :rows="3" />
        </a-form-item>
        <a-form-item label="数据文件">
          <a-upload-dragger :before-upload="() => false">
            <p class="ant-upload-drag-icon"><InboxOutlined /></p>
            <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
            <p class="ant-upload-hint">支持 JSONL / CSV / JSON / Parquet 格式</p>
          </a-upload-dragger>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, UploadOutlined, InboxOutlined } from '@ant-design/icons-vue'
import { getFinetuneTaskList, createFinetuneTask, cancelFinetuneTask, getDatasetList, createDataset } from '@/api/finetuneApi'
import { getModelList } from '@/api/modelApi'
import type { FinetuneTaskItem, DatasetItem, ModelItem } from '@/types/api'
import { formatTime } from '@/utils'

const activeTab = ref('tasks')
const tasks = ref<FinetuneTaskItem[]>([])
const datasets = ref<DatasetItem[]>([])
const models = ref<ModelItem[]>([])
const taskLoading = ref(false)
const datasetLoading = ref(false)
const taskModalOpen = ref(false)
const datasetModalOpen = ref(false)
const detailModalOpen = ref(false)
const saving = ref(false)
const datasetSaving = ref(false)
const currentTask = ref<FinetuneTaskItem | null>(null)

const taskQuery = reactive({ status: undefined as string | undefined })

const taskForm = reactive({
  name: '',
  base_model_id: undefined as number | undefined,
  dataset_id: undefined as number | undefined,
  hyper_params: { epochs: 3, learning_rate: 0.0001, batch_size: 8, lora_rank: 8, lora_alpha: 16 }
})

const datasetForm = reactive({ name: '', format: 'jsonl', description: '' })

const taskStatusMap: Record<string, string> = {
  pending: '待运行', queued: '排队中', running: '运行中', paused: '已暂停',
  completed: '已完成', failed: '失败', cancelled: '已取消', deployed: '已部署'
}
const taskStatusColorMap: Record<string, string> = {
  pending: 'default', queued: 'processing', running: 'processing', paused: 'warning',
  completed: 'success', failed: 'error', cancelled: 'default', deployed: 'cyan'
}
function taskStatusText(s: string) { return taskStatusMap[s] || s }
function taskStatusColor(s: string) { return taskStatusColorMap[s] || 'default' }

const annotationStatusMap: Record<string, string> = {
  pending: '待标注', labeling: '标注中', labeled: '已标注', reviewing: '审核中', reviewed: '已审核'
}
function annotationStatusText(s: string) { return annotationStatusMap[s] || s }

const modelOptions = computed(() => models.value.map((m) => ({ label: `${m.name} (${m.provider})`, value: m.id })))
const datasetOptions = computed(() => datasets.value.map((d) => ({ label: d.name, value: d.id })))

function getModelName(id: number) { return models.value.find((m) => m.id === id)?.name || `#${id}` }
function formatFileSize(bytes: number) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0, size = bytes
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++ }
  return `${size.toFixed(1)} ${units[i]}`
}

async function loadTasks() {
  taskLoading.value = true
  try { tasks.value = (await getFinetuneTaskList(taskQuery)) as FinetuneTaskItem[] } finally { taskLoading.value = false }
}
async function loadDatasets() {
  datasetLoading.value = true
  try { datasets.value = (await getDatasetList()) as DatasetItem[] } finally { datasetLoading.value = false }
}
async function loadModels() {
  try { models.value = (await getModelList()) as ModelItem[] } catch { /* ignore */ }
}

function openCreateTaskModal() {
  Object.assign(taskForm, { name: '', base_model_id: undefined, dataset_id: undefined, hyper_params: { epochs: 3, learning_rate: 0.0001, batch_size: 8, lora_rank: 8, lora_alpha: 16 } })
  taskModalOpen.value = true
}

async function handleCreateTask() {
  if (!taskForm.name) {
    message.warning('请输入任务名称')
    return
  }
  if (taskForm.base_model_id === undefined) {
    message.warning('请选择基座模型')
    return
  }
  if (taskForm.dataset_id === undefined) {
    message.warning('请选择数据集')
    return
  }
  saving.value = true
  try {
    await createFinetuneTask({
      name: taskForm.name,
      base_model_id: taskForm.base_model_id,
      dataset_id: taskForm.dataset_id,
      hyper_params: { ...taskForm.hyper_params }
    })
    message.success('任务创建成功，已进入队列')
    taskModalOpen.value = false
    loadTasks()
  } catch { message.error('创建失败') } finally { saving.value = false }
}

async function cancelTask(record: FinetuneTaskItem) {
  await cancelFinetuneTask(record.id)
  message.success('任务已取消')
  loadTasks()
}

function viewTaskDetail(record: FinetuneTaskItem) {
  currentTask.value = { ...record }
  if (currentTask.value.started_at) currentTask.value.started_at = formatTime(currentTask.value.started_at)
  if (currentTask.value.finished_at) currentTask.value.finished_at = formatTime(currentTask.value.finished_at)
  detailModalOpen.value = true
}

function openDatasetModal() {
  Object.assign(datasetForm, { name: '', format: 'jsonl', description: '' })
  datasetModalOpen.value = true
}

async function handleCreateDataset() {
  if (!datasetForm.name) { message.warning('请输入数据集名称'); return }
  datasetSaving.value = true
  try {
    await createDataset({ ...datasetForm })
    message.success('数据集创建成功')
    datasetModalOpen.value = false
    loadDatasets()
  } catch { message.error('创建失败') } finally { datasetSaving.value = false }
}

onMounted(() => { loadTasks(); loadDatasets(); loadModels() })
</script>
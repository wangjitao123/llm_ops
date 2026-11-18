<template>
  <div class="page-container">
    <!-- 信息横幅 -->
    <a-alert type="info" show-icon style="margin-bottom:16px">
      <template #message>
        平台集成了 <b>GPTQ</b>、<b>AWQ</b>、<b>bitsandbytes</b> 三种量化算法，利用 GPU（8×NVIDIA L20）自动执行。量化完成后的模型可直接在「模型管理」中使用。
      </template>
    </a-alert>

    <!-- 工具条 -->
    <div class="panel-card">
      <div class="table-toolbar">
        <div class="toolbar-filters">
          <a-select v-model:value="query.status" placeholder="全部状态" allow-clear style="width:130px" @change="loadTasks">
            <a-select-option v-for="(t,k) in statusMap" :key="k" :value="k">{{ t }}</a-select-option>
          </a-select>
          <a-button type="primary" @click="loadTasks">查询</a-button>
        </div>
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          创建量化任务
        </a-button>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="panel-card" style="margin-top:16px;padding:0">
      <a-table :data-source="tasks" :loading="loading" row-key="id" :pagination="{ pageSize: 20 }">
        <a-table-column title="任务名称" key="name" width="35%">
          <template #default="{ record }">
            <div style="font-weight:500">{{ record.name }}</div>
            <div style="font-size:12px;color:#8c8c8c;margin-top:2px">{{ record.hf_model_id }}</div>
          </template>
        </a-table-column>
        <a-table-column title="量化方案" key="algo" width="16%">
          <template #default="{ record }">
            <a-tag :color="tagColor(record.status)">{{ record.algorithm.toUpperCase() }} W{{ record.weight_bits }}A{{ record.activation_bits }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="状态" key="status" width="10%">
          <template #default="{ record }">
            <a-badge :status="badgeStatus(record.status)" :text="statusMap[record.status] || record.status" />
          </template>
        </a-table-column>
        <a-table-column title="进度" key="progress" width="16%">
          <template #default="{ record }">
            <a-progress :percent="record.progress" size="small" :status="record.status === 'failed' ? 'exception' : record.status === 'completed' ? 'success' : 'active'" />
          </template>
        </a-table-column>
        <a-table-column title="结果模型" key="result" width="10%">
          <template #default="{ record }">
            <a v-if="record.result_model_id" @click="goModel(record.result_model_id)" style="cursor:pointer">#{{ record.result_model_id }}</a>
            <span v-else style="color:#d9d9d9">-</span>
          </template>
        </a-table-column>
        <a-table-column title="操作" key="action" width="18%">
          <template #default="{ record }">
            <a-space>
              <a @click="viewDetail(record)">详情</a>
              <a v-if="record.status === 'pending'" @click="handleSubmit(record)">提交执行</a>
              <a v-if="['queued','running'].includes(record.status)" @click="handleCancel(record)" style="color:#ff4d4f">取消</a>
              <a v-if="record.status === 'failed'" @click="handleRetry(record)">🔄 重试</a>
              <a-popconfirm v-if="['completed','failed','cancelled'].includes(record.status)" title="确定删除？" @confirm="handleDelete(record)">
                <a style="color:#ff4d4f">删除</a>
              </a-popconfirm>
            </a-space>
          </template>
        </a-table-column>
      </a-table>
    </div>

    <!-- 创建弹窗 -->
    <a-modal v-model:open="createModal" title="创建量化任务" :confirm-loading="creating" @ok="handleCreate" width="720px">
      <!-- 快速模板 -->
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;padding:12px;background:#fafafa;border-radius:8px;border:1px solid #f0f0f0">
        <span style="font-size:13px;color:#8c8c8c;display:flex;align-items:center;gap:4px">⚡ 快速模板</span>
        <a-tag v-for="tpl in templates" :key="tpl.label" :color="tpl.recommend ? 'blue' : 'default'" style="cursor:pointer" @click="applyTemplate(tpl)">{{ tpl.label }}</a-tag>
      </div>

      <a-divider orientation="left" style="font-size:14px;font-weight:500">基本信息</a-divider>
      <a-form :model="form" layout="vertical">
        <a-form-item label="任务名称" required>
          <a-input v-model:value="form.name" placeholder="如：Qwen2.5-7B GPTQ 4bit 量化" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="14">
            <a-form-item label="HuggingFace 模型 ID" required>
              <a-input v-model:value="form.hf_model_id" placeholder="如：Qwen/Qwen2.5-7B-Instruct" />
            </a-form-item>
          </a-col>
          <a-col :span="10">
            <a-form-item label="输出模型名称（可选）">
              <a-input v-model:value="form.output_name" placeholder="留空自动生成" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-divider orientation="left" style="font-size:14px;font-weight:500">量化配置</a-divider>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="量化算法" required>
              <a-select v-model:value="form.algorithm">
                <a-select-option value="gptq">GPTQ — 通用最优</a-select-option>
                <a-select-option value="awq">AWQ — 精度保持最好</a-select-option>
                <a-select-option value="bitsandbytes">bitsandbytes — 轻量快速</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="权重精度" required>
              <a-select v-model:value="form.weight_bits">
                <a-select-option :value="2">2 bit — 极致压缩</a-select-option>
                <a-select-option :value="3">3 bit — 折中</a-select-option>
                <a-select-option :value="4">4 bit — 推荐</a-select-option>
                <a-select-option :value="8">8 bit — 近乎无损</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="分组大小" required>
              <a-select v-model:value="form.group_size">
                <a-select-option :value="32">32 — 高精度</a-select-option>
                <a-select-option :value="64">64 — 适中</a-select-option>
                <a-select-option :value="128">128 — 推荐</a-select-option>
                <a-select-option :value="256">256 — 最小体积</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>

        <a-divider orientation="left" style="font-size:14px;font-weight:500">校准数据</a-divider>
        <a-row :gutter="16">
          <a-col :span="6">
            <a-form-item label="样本数">
              <a-input-number v-model:value="form.calib_samples" :min="64" :max="1024" :step="64" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="18">
            <a-form-item label="数据来源">
              <a-radio-group v-model:value="form.calib_source" @change="onCalibSourceChange">
                <a-radio value="default">默认 wikitext-2</a-radio>
                <a-radio value="custom">自定义校准文本</a-radio>
              </a-radio-group>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item v-if="form.calib_source === 'custom'">
          <a-textarea v-model:value="form.calib_text" :rows="4" placeholder="在此粘贴校准文本，每行一条样本。&#10;示例：&#10;What is the capital of France?&#10;Explain quantum computing in simple terms." />
          <div style="margin-top:6px">
            <a-upload :before-upload="handleUpload" :show-upload-list="false" accept=".txt,.jsonl">
              <a-button size="small">📁 上传文件</a-button>
            </a-upload>
          </div>
        </a-form-item>

        <a-collapse ghost style="margin-top:8px">
          <a-collapse-panel key="adv" header="高级设置">
            <a-form-item label="输出路径（可选）">
              <a-input v-model:value="form.output_path" placeholder="留空使用默认路径 /models/" />
            </a-form-item>
          </a-collapse-panel>
        </a-collapse>
      </a-form>
    </a-modal>

    <!-- 详情弹窗 -->
    <a-modal v-model:open="detailModal" title="任务详情" footer="关闭" width="680px" @cancel="closeDetail">
      <a-descriptions v-if="currentTask" :column="2" bordered size="small">
        <a-descriptions-item label="任务名称" :span="2">{{ currentTask.name }}</a-descriptions-item>
        <a-descriptions-item label="基座模型" :span="2"><a-tag>{{ currentTask.hf_model_id }}</a-tag></a-descriptions-item>
        <a-descriptions-item label="量化算法">{{ currentTask.algorithm.toUpperCase() }}</a-descriptions-item>
        <a-descriptions-item label="精度">W{{ currentTask.weight_bits }}A{{ currentTask.activation_bits }}</a-descriptions-item>
        <a-descriptions-item label="分组大小">{{ currentTask.group_size }}</a-descriptions-item>
        <a-descriptions-item label="校准数据">{{ currentTask.calib_samples }} 条（{{ currentTask.calib_source === 'custom' ? '自定义' : '默认 wikitext' }}）</a-descriptions-item>
        <a-descriptions-item label="状态"><a-badge :status="badgeStatus(currentTask.status)" :text="statusMap[currentTask.status]" /></a-descriptions-item>
        <a-descriptions-item label="进度">{{ currentTask.progress }}%</a-descriptions-item>
        <a-descriptions-item label="输出路径" :span="2"><a-tag v-if="currentTask.output_path">{{ currentTask.output_path }}</a-tag><span v-else>-</span></a-descriptions-item>
        <a-descriptions-item label="结果模型" :span="2">
          <a v-if="currentTask.result_model_id" @click="goModel(currentTask.result_model_id)" style="cursor:pointer">模型 #{{ currentTask.result_model_id }} →</a>
          <span v-else>-</span>
        </a-descriptions-item>
        <a-descriptions-item v-if="currentTask.error_message" label="错误信息" :span="2">
          <a-typography-text type="danger">{{ currentTask.error_message }}</a-typography-text>
        </a-descriptions-item>
        <a-descriptions-item label="创建人">{{ currentTask.created_by }}</a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ currentTask.created_at }}</a-descriptions-item>
      </a-descriptions>

      <!-- 运行日志 -->
      <a-divider style="margin-top:16px" />
      <div style="font-weight:500;margin-bottom:8px">📋 运行日志</div>
      <div ref="logRef" style="background:#1a1a2e;color:#d4d4d4;border-radius:8px;padding:14px;font-family:'Consolas',monospace;font-size:13px;line-height:1.7;max-height:220px;overflow-y:auto">
        <div v-for="(line,i) in logLines" :key="i" style="white-space:pre-wrap">
          <span v-if="line.time" style="color:#6a9955">{{ line.time }}</span>
          <span v-if="line.level === 'err'" style="color:#f44747;margin:0 4px">ERROR</span>
          <span v-else-if="line.level === 'warn'" style="color:#dcdcaa;margin:0 4px">WARN</span>
          <span v-else-if="line.level === 'ok'" style="color:#52c41a;margin:0 4px">SUCCESS</span>
          <span v-else-if="line.level === 'info'" style="color:#569cd6;margin:0 4px">INFO</span>
          <span v-else style="margin:0 4px">{{ line.level }}</span>
          <span :style="{color: line.level === 'dim' ? '#6a6a8a' : '#d4d4d4', fontStyle: line.level === 'dim' ? 'italic' : 'normal'}">{{ line.msg }}</span>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { getTaskList, createTask, submitTask, cancelTask, deleteTask } from '@/api/quantizationApi'
import type { QuantizationTask } from '@/types/api'

const statusMap: Record<string, string> = {
  pending: '待提交',
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const templates = [
  { label: 'W4A16-GPTQ ★', algorithm: 'gptq', weight_bits: 4, group_size: 128, recommend: true },
  { label: 'W4A16-AWQ', algorithm: 'awq', weight_bits: 4, group_size: 128 },
  { label: 'W4A16-bnb', algorithm: 'bitsandbytes', weight_bits: 4, group_size: 64 },
  { label: 'W8A16-GPTQ', algorithm: 'gptq', weight_bits: 8, group_size: 128 },
  { label: 'W3A16-AWQ 极限', algorithm: 'awq', weight_bits: 3, group_size: 128 },
]

function tagColor(status: string): string {
  return { pending: 'default', queued: 'blue', running: 'orange', completed: 'green', failed: 'red', cancelled: 'default' }[status] || 'default'
}
function badgeStatus(status: string): 'default' | 'processing' | 'success' | 'error' | 'warning' {
  return { pending: 'default', queued: 'processing', running: 'processing', completed: 'success', failed: 'error', cancelled: 'default' }[status] as any || 'default'
}

const tasks = ref<QuantizationTask[]>([])
const loading = ref(false)
const query = reactive<{ status?: string }>({})

// 创建
const createModal = ref(false)
const creating = ref(false)
const form = reactive({
  name: '',
  hf_model_id: '',
  output_name: '',
  algorithm: 'gptq',
  weight_bits: 4,
  group_size: 128,
  calib_samples: 256,
  calib_source: 'default',
  calib_text: '',
  output_path: '',
})

// 详情
const detailModal = ref(false)
const currentTask = ref<QuantizationTask | null>(null)
const logLines = ref<Array<{time:string;level:string;msg:string}>>([])

// 模拟日志（按状态）
const mockLogs: Record<string, Array<{time:string;level:string;msg:string}>> = {
  pending: [{ time: '--:--:--', level: 'dim', msg: '等待提交执行...' }],
  queued: [{ time: '--:--:--', level: 'dim', msg: '任务排队中，等待 GPU Worker 调度...' }],
  running: [
    { time: '[10:30:01]', level: 'info', msg: '开始量化任务' },
    { time: '[10:30:03]', level: 'info', msg: '从 HuggingFace 下载模型 ...' },
    { time: '[10:32:15]', level: 'info', msg: '模型下载完成' },
    { time: '[10:32:20]', level: 'info', msg: '开始量化 (W4A16, group_size=128)' },
    { time: '[10:35:40]', level: 'info', msg: '量化进度 45% — 处理第 45/100 个 block' },
    { time: '[10:35:41]', level: 'info', msg: '显存: 12.4GB / 48GB (L20)' },
    { time: '--:--:--', level: 'dim', msg: '任务运行中，日志持续更新...' },
  ],
  completed: [
    { time: '[10:30:01]', level: 'info', msg: '开始量化任务' },
    { time: '[10:32:15]', level: 'info', msg: '模型下载完成' },
    { time: '[10:50:20]', level: 'info', msg: '量化完成！模型已保存' },
    { time: '[10:50:22]', level: 'info', msg: '注册量化模型到平台' },
    { time: '[10:50:25]', level: 'ok', msg: '任务完成，总耗时 20 分 24 秒' },
  ],
  failed: [
    { time: '[09:00:01]', level: 'info', msg: '开始量化任务' },
    { time: '[09:05:30]', level: 'info', msg: '开始量化' },
    { time: '[09:12:18]', level: 'warn', msg: '显存占用: 21.6GB / 48GB' },
    { time: '[09:12:20]', level: 'err', msg: 'CUDA out of memory' },
  ],
  cancelled: [{ time: '--:--:--', level: 'dim', msg: '任务已取消' }],
}

async function loadTasks() {
  loading.value = true
  try {
    tasks.value = (await getTaskList(query.status)) as QuantizationTask[]
  } catch { message.error('加载失败') }
  finally { loading.value = false }
}

function openCreate() {
  form.name = ''
  form.hf_model_id = ''
  form.output_name = ''
  form.algorithm = 'gptq'
  form.weight_bits = 4
  form.group_size = 128
  form.calib_samples = 256
  form.calib_source = 'default'
  form.calib_text = ''
  form.output_path = ''
  createModal.value = true
}

function applyTemplate(tpl: typeof templates[0]) {
  form.algorithm = tpl.algorithm
  form.weight_bits = tpl.weight_bits
  form.group_size = tpl.group_size
}

function onCalibSourceChange() {}

function handleUpload(file: File): boolean {
  const reader = new FileReader()
  reader.onload = (e) => {
    const text = e.target?.result as string
    if (text) form.calib_text = text.slice(0, 3000) + (text.length > 3000 ? '\n...（文件截断，仅取前 3000 字符）' : '')
  }
  reader.readAsText(file.slice(0, 102400)) // 最多 100KB
  message.success(`已上传: ${file.name}`)
  return false
}

async function handleCreate() {
  if (!form.name.trim()) { message.warning('请输入任务名称'); return }
  if (!form.hf_model_id.trim()) { message.warning('请输入 HuggingFace 模型 ID'); return }
  creating.value = true
  try {
    await createTask({ ...form, activation_bits: 16, base_model_id: null })
    message.success('创建成功，已提交到 GPU Worker')
    createModal.value = false
    loadTasks()
  } catch { message.error('创建失败') }
  finally { creating.value = false }
}

async function handleSubmit(record: QuantizationTask) {
  try {
    await submitTask(record.id)
    message.success('任务已提交')
    loadTasks()
  } catch { message.error('提交失败') }
}

async function handleCancel(record: QuantizationTask) {
  try {
    await cancelTask(record.id)
    message.success('任务已取消')
    loadTasks()
  } catch { message.error('取消失败') }
}

async function handleRetry(record: QuantizationTask) {
  try {
    const { retryTask } = await import('@/api/quantizationApi')
    await retryTask(record.id)
    message.success('任务已重试')
    loadTasks()
  } catch { message.error('重试失败') }
}

async function handleDelete(record: QuantizationTask) {
  try {
    await deleteTask(record.id)
    loadTasks()
  } catch { message.error('删除失败') }
}

function viewDetail(record: QuantizationTask) {
  currentTask.value = record
  logLines.value = mockLogs[record.status] || mockLogs.pending
  detailModal.value = true
}

function closeDetail() {
  detailModal.value = false
  currentTask.value = null
}

function goModel(_id: number) {
  window.location.href = '/models'
}

onMounted(loadTasks)
</script>
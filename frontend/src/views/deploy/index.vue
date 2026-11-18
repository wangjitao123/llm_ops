<template>
  <div class="page-container">
    <div class="panel-card">
      <div class="table-toolbar">
        <div class="toolbar-filters">
          <a-select v-model:value="query.status" placeholder="全部状态" allow-clear style="width:130px" @change="loadDeployments">
            <a-select-option v-for="(t,k) in statusMap" :key="k" :value="k">{{ t }}</a-select-option>
          </a-select>
          <a-select v-model:value="query.deploy_type" placeholder="全部运行方式" allow-clear style="width:150px" @change="loadDeployments">
            <a-select-option value="managed">平台管理</a-select-option>
            <a-select-option value="conda">Conda 环境</a-select-option>
            <a-select-option value="docker">Docker 容器</a-select-option>
            <a-select-option value="other">其他</a-select-option>
          </a-select>
          <a-input-search v-model:value="query.search" placeholder="搜索名称..." style="width:200px" @search="loadDeployments" />
          <a-button @click="loadDeployments">查询</a-button>
        </div>
        <div class="toolbar-actions">
          <a-button @click="openRegister">
            <template #icon><PlusCircleOutlined /></template>
            注册已有端点
          </a-button>
          <a-button type="primary" @click="openCreate">
            <template #icon><RocketOutlined /></template>
            新建部署
          </a-button>
        </div>
      </div>
    </div>

    <!-- Stats -->
    <a-row :gutter="16" style="margin:16px 0">
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="总部署数" :value="stats.total" :value-style="{color:'#1890ff'}" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="运行中" :value="stats.running" :value-style="{color:'#52c41a'}" suffix="/ 正常" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="GPU 占用" :value="stats.gpu_used" suffix="GB" :precision="1" :value-style="{color:'#faad14'}" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="异常部署" :value="stats.abnormal" :value-style="{color:stats.abnormal>0?'#ff4d4f':'#8c8c8c'}" />
        </a-card>
      </a-col>
    </a-row>

    <!-- Deployment table -->
    <div class="panel-card" style="padding:0">
      <a-table :data-source="deployments" :loading="loading" row-key="id" :pagination="{pageSize:20}">
        <a-table-column title="部署名称" key="name" width="18%">
          <template #default="{record}">
            <a @click="openDetail(record)" style="font-weight:500">{{ record.name }}</a>
            <div style="font-size:12px;color:#8c8c8c">{{ record.hf_model_id || ('模型 #'+record.base_model_id) }}</div>
          </template>
        </a-table-column>
        <a-table-column title="运行方式" key="deploy_type" width="10%">
          <template #default="{record}">
            <a-tag :color="deployTypeColor(record.deploy_type)">{{ deployTypeLabel(record.deploy_type) }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="状态" key="status" width="8%">
          <template #default="{record}">
            <a-badge :status="badgeStatus(record.status)" :text="statusMap[record.status]||record.status" />
          </template>
        </a-table-column>
        <a-table-column title="引擎" key="engine" width="8%">
          <template #default="{record}">
            <span v-if="record.engine" style="font-family:monospace;font-size:12px">{{ record.engine.toUpperCase() }}</span>
            <span v-else style="color:#d9d9d9">-</span>
          </template>
        </a-table-column>
        <a-table-column title="端点 URL" key="endpoint_url" width="16%">
          <template #default="{record}">
            <code style="font-size:11px">{{ shortUrl(record.endpoint_url) }}</code>
          </template>
        </a-table-column>
        <a-table-column title="配置摘要" key="config" width="16%">
          <template #default="{record}">
            <a-tag v-if="record.tools_json?.length" style="font-size:11px">🔧 tools: {{ record.tools_json.length }}</a-tag>
            <a-tag v-if="record.system_prompt" style="font-size:11px">📝 prompt</a-tag>
            <a-tag v-if="record.web_search_enabled" style="font-size:11px">🌐 search</a-tag>
            <span v-if="!record.tools_json?.length && !record.system_prompt && !record.web_search_enabled" style="color:#d9d9d9">-</span>
          </template>
        </a-table-column>
        <a-table-column title="健康" key="health" width="8%">
          <template #default="{record}">
            <a-tooltip v-if="record.status==='running'" title="最近 1 小时健康率"><a-badge status="success" /> {{ record.health_rate || 100 }}%</a-tooltip>
            <a-tag v-else-if="record.status==='failed'" color="red">异常</a-tag>
            <span v-else style="color:#d9d9d9">-</span>
          </template>
        </a-table-column>
        <a-table-column title="操作" key="action" width="16%">
          <template #default="{record}">
            <a-space>
              <a @click="openDetail(record)">详情</a>
              <a-popconfirm v-if="record.deploy_type==='managed' && record.status==='running'" title="确定停止？" @confirm="handleStop(record)">
                <a style="color:#ff4d4f">停止</a>
              </a-popconfirm>
              <a-popconfirm v-if="record.deploy_type==='managed' && record.status==='stopped'" title="确定启动？" @confirm="handleStart(record)">
                <a style="color:#52c41a">启动</a>
              </a-popconfirm>
              <a v-if="record.deploy_type==='managed' && ['running','stopped','failed'].includes(record.status)" @click="handleRestart(record)">重启</a>
              <a-popconfirm v-if="record.status==='failed'" title="确定重试？" @confirm="handleRetry(record)">
                <a style="color:#faad14">重试</a>
              </a-popconfirm>
              <a-popconfirm v-if="['stopped','failed'].includes(record.status)" title="确定删除？" @confirm="handleDelete(record)">
                <a style="color:#ff4d4f">删除</a>
              </a-popconfirm>
            </a-space>
          </template>
        </a-table-column>
      </a-table>
    </div>

    <!-- GPU Topology -->
    <div class="panel-card" style="margin-top:16px">
      <div class="d-flex align-items-center gap-2" style="margin-bottom:12px">
        <h5 style="margin:0;font-size:14px;font-weight:600"><DashboardOutlined /> GPU 资源拓扑</h5>
        <a-tag v-if="gpuInfo.source" style="font-size:11px" color="blue">来源: {{ gpuInfo.source }}</a-tag>
        <a-tag v-if="gpuInfo.updated_at" style="font-size:11px">更新: {{ shortTime(gpuInfo.updated_at) }}</a-tag>
        <a-button size="small" type="link" :loading="gpuLoading" @click="loadGpuTopology">刷新</a-button>
      </div>
      <a-alert
        v-if="!gpuInfo.available"
        type="warning"
        show-icon
        :message="gpuInfo.error || '当前无法采集 GPU 信息'"
        description="GPU 采集由带显卡的 worker 执行。若刚部署完，请等 30 秒后刷新；或检查 GPU worker 是否正常运行。"
      />
      <a-row v-else :gutter="8">
        <a-col v-for="g in gpuTopology" :key="g.gpu_id" :span="3">
          <a-card size="small" style="text-align:center;border-color:g.memory_used_gb>40?'#ff4d4f':g.memory_used_gb>20?'#faad14':'#e8e8e8'">
            <div style="font-weight:600">GPU {{ g.gpu_id }}</div>
            <div><a-progress type="dashboard" :percent="gpuPercent(g)" :size="60" /></div>
            <small>{{ g.memory_used_gb.toFixed(1) }}/{{ g.memory_total_gb }}GB</small>
            <div v-if="g.deployments.length" style="font-size:10px;color:#8c8c8c;margin-top:4px">{{ g.deployments.join(', ') }}</div>
          </a-card>
        </a-col>
      </a-row>
    </div>

    <!-- ====== REGISTER MODAL ====== -->
    <a-modal v-model:open="registerModal" title="注册已有端点" :confirm-loading="registerLoading" @ok="handleRegister" width="700px">
      <p style="color:#8c8c8c;font-size:13px">适用于已经在 conda 环境或 Docker 容器中运行的模型。平台负责健康检查和网关集成，不管理进程生命周期。</p>
      <a-form :model="registerForm" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="部署名称" required>
              <a-input v-model:value="registerForm.name" placeholder="如: deepseek-r1-production" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="运行方式" required>
              <a-select v-model:value="registerForm.deploy_type">
                <a-select-option value="conda">Conda 环境</a-select-option>
                <a-select-option value="docker">Docker 容器</a-select-option>
                <a-select-option value="other">其他</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="端点 URL" required>
          <a-input v-model:value="registerForm.endpoint_url" placeholder="http://10.51.13.7:31000/v1/chat/completions" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="基座模型">
              <a-input v-model:value="registerForm.hf_model_id" placeholder="如: Qwen/Qwen2.5-7B-Instruct" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="推理引擎">
              <a-select v-model:value="registerForm.engine" allow-clear>
                <a-select-option value="vllm">vLLM</a-select-option>
                <a-select-option value="tgi">TGI</a-select-option>
                <a-select-option value="sglang">SGLang</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-divider />
        <h5 style="font-size:14px;font-weight:600">配置（可选，注册后可修改）</h5>
        <a-form-item label="System Prompt">
          <a-textarea v-model:value="registerForm.system_prompt" :rows="3" placeholder="可选，网关自动注入到请求前" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="Temperature">
              <a-input-number v-model:value="registerForm.temperature" :min="0" :max="2" :step="0.1" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="Max Tokens">
              <a-input-number v-model:value="registerForm.max_tokens" :min="64" :max="131072" :step="512" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="Top P">
              <a-input-number v-model:value="registerForm.top_p" :min="0" :max="1" :step="0.1" style="width:100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item>
          <a-checkbox v-model:checked="registerForm.health_check_enabled">启用健康检查</a-checkbox>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- ====== CREATE MODAL ====== -->
    <a-modal v-model:open="createModal" title="新建模型部署" :confirm-loading="creating" @ok="handleCreate" width="600px">
      <div style="background:#fafafa;border-radius:8px;padding:12px;border:1px solid #f0f0f0;margin-bottom:16px">
        <span style="font-size:13px;color:#8c8c8c">⚡ 快速模板</span>
        <div style="margin-top:4px">
          <a-tag v-for="tpl in templates" :key="tpl.label" :color="tpl.recommend?'blue':'default'" style="cursor:pointer" @click="applyTemplate(tpl)">{{ tpl.label }}</a-tag>
        </div>
      </div>
      <a-form :model="createForm" layout="vertical">
        <a-form-item label="模型来源">
          <a-radio-group v-model:value="createForm.source" @change="onCreateSourceChange">
            <a-radio value="quantized">量化完成</a-radio>
            <a-radio value="hf">HuggingFace</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="createForm.source==='quantized'" label="选择量化模型">
          <a-select v-model:value="createForm.quantized_task_id" placeholder="—— 选择量化任务 ——">
            <a-select-option v-for="q in quantizedModels" :key="q.task_id" :value="q.task_id">{{ q.task_name }} ({{ q.hf_model_id }} · {{ q.algorithm.toUpperCase() }} W{{ q.weight_bits }})</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item v-else label="HuggingFace 模型 ID">
          <a-input v-model:value="createForm.hf_model_id" placeholder="如: Qwen/Qwen2.5-7B-Instruct" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="部署名称" required>
              <a-input v-model:value="createForm.name" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="推理引擎">
              <a-select v-model:value="createForm.engine">
                <a-select-option value="vllm">vLLM (推荐)</a-select-option>
                <a-select-option value="tgi">TGI</a-select-option>
                <a-select-option value="sglang">SGLang</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="GPU 数量">
              <a-select v-model:value="createForm.gpu_count">
                <a-select-option :value="1">1 卡</a-select-option>
                <a-select-option :value="2">2 卡 TP</a-select-option>
                <a-select-option :value="4">4 卡 TP</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="最大并发">
              <a-input-number v-model:value="createForm.max_concurrency" :min="1" :max="1024" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="Max Tokens">
              <a-input-number v-model:value="createForm.max_input_tokens" :min="256" :max="131072" style="width:100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item>
          <a-checkbox v-model:checked="createForm.auto_register">部署完成后自动注册到「模型管理」</a-checkbox>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- ====== DETAIL MODAL ====== -->
    <a-modal v-model:open="detailModal" :title="'部署详情 - '+(current?.name||'')" footer="关闭" width="720px" @cancel="closeDetail">
      <template v-if="current">
        <a-descriptions :column="2" bordered size="small">
          <a-descriptions-item label="端点 URL" :span="2">{{ current.endpoint_url }}</a-descriptions-item>
          <a-descriptions-item label="运行方式"><a-tag :color="deployTypeColor(current.deploy_type)">{{ deployTypeLabel(current.deploy_type) }}</a-tag></a-descriptions-item>
          <a-descriptions-item label="引擎">{{ current.engine?.toUpperCase() || '-' }}</a-descriptions-item>
          <a-descriptions-item label="基座模型" :span="2">{{ current.hf_model_id || ('模型 #'+current.base_model_id) || '-' }}</a-descriptions-item>
          <a-descriptions-item label="状态"><a-badge :status="badgeStatus(current.status)" :text="statusMap[current.status]||current.status" /></a-descriptions-item>
          <a-descriptions-item label="GPU">{{ current.gpu_count }} 卡 · {{ current.gpu_memory_gb||'-' }}GB</a-descriptions-item>
          <a-descriptions-item label="创建人">{{ current.created_by }}</a-descriptions-item>
          <a-descriptions-item label="创建时间">{{ current.created_at }}</a-descriptions-item>
          <a-descriptions-item v-if="current.error_message" label="错误信息" :span="2">
            <a-typography-text type="danger">{{ current.error_message }}</a-typography-text>
          </a-descriptions-item>
        </a-descriptions>

        <!-- Config summary -->
        <a-divider style="margin:12px 0" />
        <h5 style="font-size:14px;font-weight:600">当前配置</h5>
        <div style="display:flex;flex-wrap:wrap;gap:6px">
          <a-tag v-if="current.temperature">temperature: {{ current.temperature }}</a-tag>
          <a-tag v-if="current.max_tokens">max_tokens: {{ current.max_tokens }}</a-tag>
          <a-tag v-if="current.top_p">top_p: {{ current.top_p }}</a-tag>
          <a-tag v-if="current.system_prompt" color="blue">system_prompt: 已配置</a-tag>
          <a-tag v-if="current.tools_json?.length" color="purple">tools: {{ current.tools_json.length }} 个</a-tag>
          <a-tag v-if="current.web_search_enabled" color="green">web_search: 已启用</a-tag>
        </div>
        <a-space style="margin-top:8px">
          <a-button size="small" @click="editConfig(current)"><template #icon><SettingOutlined /></template>编辑配置</a-button>
          <a-button size="small" @click="fetchLogs(current.id)"><template #icon><FileTextOutlined /></template>查看日志</a-button>
        </a-space>

        <!-- Logs -->
        <a-divider style="margin:12px 0" />
        <h5 style="font-size:14px;font-weight:600">运行日志</h5>
        <div ref="logRef" style="background:#1a1a2e;color:#d4d4d4;border-radius:8px;padding:14px;font-family:'Consolas',monospace;font-size:13px;line-height:1.7;max-height:220px;overflow-y:auto">
          <div v-for="(line,i) in logLines" :key="i" style="white-space:pre-wrap">
            <span v-if="line.time" style="color:#6a9955">{{ line.time }}</span>
            <span v-if="line.level==='err'" style="color:#f44747;margin:0 4px">ERROR</span>
            <span v-else-if="line.level==='warn'" style="color:#dcdcaa;margin:0 4px">WARN</span>
            <span v-else-if="line.level==='ok'" style="color:#52c41a;margin:0 4px">OK</span>
            <span v-else style="color:#569cd6;margin:0 4px">INFO</span>
            <span :style="{color:line.level==='dim'?'#6a6a8a':'#d4d4d4'}">{{ line.msg }}</span>
          </div>
        </div>
      </template>
    </a-modal>

    <!-- ====== CONFIG EDITOR MODAL ====== -->
    <a-modal v-model:open="configModal" title="编辑部署配置" :confirm-loading="configSaving" @ok="saveConfig" width="680px">
      <a-form :model="configForm" layout="vertical">
        <a-form-item label="System Prompt">
          <a-textarea v-model:value="configForm.system_prompt" :rows="3" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="6"><a-form-item label="Temperature"><a-input-number v-model:value="configForm.temperature" :min="0" :max="2" :step="0.1" style="width:100%" /></a-form-item></a-col>
          <a-col :span="6"><a-form-item label="Top P"><a-input-number v-model:value="configForm.top_p" :min="0" :max="1" :step="0.1" style="width:100%" /></a-form-item></a-col>
          <a-col :span="6"><a-form-item label="Max Tokens"><a-input-number v-model:value="configForm.max_tokens" :min="64" :max="131072" style="width:100%" /></a-form-item></a-col>
          <a-col :span="6"><a-form-item label="Freq Penalty"><a-input-number v-model:value="configForm.frequency_penalty" :min="-2" :max="2" :step="0.1" style="width:100%" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="工具调用 (Tool Call)">
          <a-button size="small" @click="addTool">+ 添加工具</a-button>
          <div v-for="(tool,i) in configForm.tools_json" :key="i" style="display:flex;gap:8px;margin-top:6px">
            <a-input v-model:value="tool.name" placeholder="工具名称" style="width:150px" />
            <a-input v-model:value="tool.description" placeholder="描述" style="flex:1" />
            <a-button size="small" danger @click="configForm.tools_json.splice(i,1)">删除</a-button>
          </div>
        </a-form-item>
        <a-form-item label="Web Search">
          <a-checkbox v-model:checked="configForm.web_search_enabled">启用 Web Search</a-checkbox>
          <div v-if="configForm.web_search_enabled" style="margin-top:8px;display:flex;gap:8px">
            <a-input v-model:value="configForm.web_search_config.api_url" placeholder="搜索 API URL" style="flex:1" />
            <a-input v-model:value="configForm.web_search_config.api_key" placeholder="API Key" type="password" style="width:200px" />
          </div>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { PlusCircleOutlined, RocketOutlined, DashboardOutlined, SettingOutlined, FileTextOutlined } from '@ant-design/icons-vue'
import { getDeployList, createDeploy, updateDeploy, deleteDeploy, startDeploy, stopDeploy, restartDeploy, getGpuTopology, getQuantizedModels } from '@/api/deployApi'
import type { DeploymentItem } from '@/types/api'

const statusMap: Record<string,string> = {
  deploying: '部署中', running: '运行中', stopped: '已停止', failed: '异常', deleted: '已删除'
}

function deployTypeColor(t: string): string {
  return { managed: 'green', conda: 'orange', docker: 'blue', other: 'default' }[t] || 'default'
}
function deployTypeLabel(t: string): string {
  return { managed: '平台管理', conda: 'Conda 环境', docker: 'Docker 容器', other: '其他' }[t] || t
}
function badgeStatus(s: string): 'success'|'processing'|'error'|'warning'|'default' {
  const m: Record<string,'success'|'processing'|'error'|'warning'|'default'> = { running: 'success', deploying: 'processing', stopped: 'default', failed: 'error' }
  return m[s] || 'default'
}
function shortUrl(url: string): string {
  if (!url) return '-'
  return url.replace(/^https?:\/\//, '').slice(0, 35)
}

const loading = ref(false)
const deployments = ref<DeploymentItem[]>([])
const query = reactive<{status?:string;deploy_type?:string;search?:string}>({})
const stats = reactive({ total:0, running:0, gpu_used:0, abnormal:0 })

interface GpuItem { gpu_id:number; memory_total_gb:number; memory_used_gb:number; memory_free_gb:number; deployments:string[] }
const gpuTopology = ref<GpuItem[]>([])
const gpuInfo = reactive<{available:boolean; source:string|null; error:string|null; updated_at:string|null}>({
  available: false, source: null, error: null, updated_at: null,
})
const gpuLoading = ref(false)

function gpuPercent(g: GpuItem): number {
  if (!g.memory_total_gb) return 0
  return Math.min(100, Math.round((g.memory_used_gb / g.memory_total_gb) * 100))
}
function shortTime(ts?: string | null): string {
  if (!ts) return '-'
  return ts.replace('T', ' ').slice(0, 19)
}

async function loadGpuTopology() {
  gpuLoading.value = true
  try {
    const res: any = await getGpuTopology()
    gpuInfo.available = !!res?.available
    gpuInfo.source = res?.source ?? null
    gpuInfo.error = res?.error ?? null
    gpuInfo.updated_at = res?.updated_at ?? null
    gpuTopology.value = (res?.gpus ?? []) as GpuItem[]
  } catch (e: any) {
    gpuInfo.available = false
    gpuInfo.error = e?.message || '获取 GPU 拓扑失败'
    gpuTopology.value = []
  } finally {
    gpuLoading.value = false
  }
}

async function loadDeployments() {
  loading.value = true
  try {
    deployments.value = (await getDeployList(query.status, query.deploy_type, query.search)) as DeploymentItem[]
  } catch {
    deployments.value = []
  } finally {
    loading.value = false
  }
  calcStats()
}
function calcStats() {
  stats.total = deployments.value.length
  stats.running = deployments.value.filter(d => d.status === 'running').length
  stats.abnormal = deployments.value.filter(d => d.status === 'failed').length
  stats.gpu_used = deployments.value.reduce((s,d) => s + (d.gpu_memory_gb || 0), 0)
}

// Register
const registerModal = ref(false)
const registerLoading = ref(false)
const registerForm = reactive({
  name:'', deploy_type:'conda', endpoint_url:'', hf_model_id:'', engine:undefined as string|undefined,
  system_prompt:'', temperature:0.7, max_tokens:4096, top_p:0.9,
  health_check_enabled:true,
})
function openRegister() {
  Object.assign(registerForm, { name:'', deploy_type:'conda', endpoint_url:'', hf_model_id:'', system_prompt:'', temperature:0.7, max_tokens:4096, top_p:0.9, health_check_enabled:true })
  registerModal.value = true
}
async function handleRegister() {
  if (!registerForm.name || !registerForm.endpoint_url) { message.warning('请填写必填项'); return }
  registerLoading.value = true
  try {
    await createDeploy({ ...registerForm, auto_register:true })
    message.success('端点已注册')
    registerModal.value = false
    loadDeployments()
  } catch { message.error('注册失败') }
  finally { registerLoading.value = false }
}

// Create
const createModal = ref(false)
const creating = ref(false)
const quantizedModels = ref<Array<{task_id:number;task_name:string;hf_model_id:string;algorithm:string;weight_bits:number;output_path:string}>>([])
const templates = [
  { label:'7B GPTQ · 单卡 ★', engine:'vllm', gpu_count:1, max_concurrency:32, max_input_tokens:4096, recommend:true },
  { label:'7B AWQ · 单卡', engine:'vllm', gpu_count:1, max_concurrency:32, max_input_tokens:4096 },
  { label:'14B AWQ · 2卡 TP', engine:'vllm', gpu_count:2, max_concurrency:64, max_input_tokens:8192 },
  { label:'32B GPTQ · 4卡 TP', engine:'vllm', gpu_count:4, max_concurrency:128, max_input_tokens:8192 },
]
const createForm = reactive({
  source:'quantized', quantized_task_id:undefined as number|undefined, hf_model_id:'',
  name:'', engine:'vllm', gpu_count:1, max_concurrency:32, max_input_tokens:4096, auto_register:true,
})
async function openCreate() {
  Object.assign(createForm, { source:'quantized', quantized_task_id:undefined, hf_model_id:'', name:'', engine:'vllm', gpu_count:1, max_concurrency:32, max_input_tokens:4096, auto_register:true })
  createModal.value = true
  try {
    const res: any = await getQuantizedModels()
    quantizedModels.value = Array.isArray(res) ? res : []
  } catch {
    quantizedModels.value = []
  }
}
function applyTemplate(tpl: typeof templates[0]) {
  createForm.engine = tpl.engine
  createForm.gpu_count = tpl.gpu_count
  createForm.max_concurrency = tpl.max_concurrency
  createForm.max_input_tokens = tpl.max_input_tokens
}
function onCreateSourceChange() {}
async function handleCreate() {
  if (!createForm.name) { message.warning('请输入部署名称'); return }
  creating.value = true
  try {
    const payload: any = {
      name: createForm.name,
      deploy_type: 'managed',
      endpoint_url: '',
      engine: createForm.engine,
      gpu_count: createForm.gpu_count,
      max_concurrency: createForm.max_concurrency,
      max_input_tokens: createForm.max_input_tokens,
      auto_register: createForm.auto_register,
    }
    if (createForm.source === 'quantized') {
      const picked = quantizedModels.value.find(q => q.task_id === createForm.quantized_task_id)
      if (!picked) { message.warning('请选择要部署的量化模型'); creating.value = false; return }
      payload.base_model_id = picked.task_id
      payload.hf_model_id = picked.hf_model_id
      payload.model_path = picked.output_path
    } else {
      if (!createForm.hf_model_id) { message.warning('请填写 HuggingFace 模型 ID'); creating.value = false; return }
      payload.hf_model_id = createForm.hf_model_id
    }
    await createDeploy(payload)
    message.success('部署任务已提交！可在列表中查看进度')
    createModal.value = false
    loadDeployments()
  } catch (e: any) { message.error(e?.message || '创建失败') }
  finally { creating.value = false }
}

// Detail
const detailModal = ref(false)
const current = ref<DeploymentItem | null>(null)
const logLines = ref<Array<{time:string;level:string;msg:string}>>([])
function openDetail(record: DeploymentItem) {
  current.value = record
  logLines.value = [
    { time:'[10:30:01]', level:'info', msg:'Starting vLLM server...' },
    { time:'[10:31:15]', level:'info', msg:'Model loaded, GPU mem: 13.4GB' },
    { time:'[10:31:22]', level:'ok', msg:'Server ready' },
    { time:'[10:31:25]', level:'info', msg:'Registered to model management' },
  ]
  detailModal.value = true
}
function closeDetail() { detailModal.value = false; current.value = null }
function fetchLogs(_id: number) { message.info('日志刷新中...') }

// Edit config
const configModal = ref(false)
const configSaving = ref(false)
const configForm = reactive({
  system_prompt:'', temperature:0.7, top_p:0.9, max_tokens:4096, frequency_penalty:0,
  tools_json:[] as Array<{name:string;description:string}>,
  web_search_enabled:false, web_search_config:{api_url:'', api_key:''},
})
function editConfig(record: DeploymentItem) {
  configForm.system_prompt = record.system_prompt || ''
  configForm.temperature = record.temperature ?? 0.7
  configForm.top_p = record.top_p ?? 0.9
  configForm.max_tokens = record.max_tokens || 4096
  configForm.frequency_penalty = record.frequency_penalty ?? 0
  configForm.tools_json = (record.tools_json || []).map(t => ({name:t.name||'', description:t.description||''}))
  configForm.web_search_enabled = record.web_search_enabled || false
  configForm.web_search_config = { api_url: record.web_search_config?.api_url || '', api_key: record.web_search_config?.api_key || '' }
  configModal.value = true
}
function addTool() { configForm.tools_json.push({name:'', description:''}) }
async function saveConfig() {
  if (!current.value) return
  configSaving.value = true
  try {
    await updateDeploy(current.value.id, {
      system_prompt: configForm.system_prompt || null,
      temperature: configForm.temperature,
      top_p: configForm.top_p,
      max_tokens: configForm.max_tokens,
      frequency_penalty: configForm.frequency_penalty,
      tools_json: configForm.tools_json.length ? configForm.tools_json : null,
      web_search_enabled: configForm.web_search_enabled,
      web_search_config: configForm.web_search_enabled ? configForm.web_search_config : null,
    } as any)
    message.success('配置已保存')
    configModal.value = false
    loadDeployments()
  } catch { message.error('保存失败') }
  finally { configSaving.value = false }
}

// Actions
async function handleStop(record: DeploymentItem) {
  try { await stopDeploy(record.id); message.success('已停止'); loadDeployments(); loadGpuTopology() }
  catch (e: any) { message.error(e?.message || '停止失败') }
}
async function handleStart(record: DeploymentItem) {
  try { await startDeploy(record.id); message.success('已启动，正在拉起容器'); loadDeployments() }
  catch (e: any) { message.error(e?.message || '启动失败') }
}
async function handleRestart(record: DeploymentItem) {
  try { await restartDeploy(record.id); message.success('正在重启'); loadDeployments() }
  catch (e: any) { message.error(e?.message || '重启失败') }
}
async function handleRetry(record: DeploymentItem) {
  try {
    await restartDeploy(record.id)
    message.success('已重试')
    loadDeployments()
  } catch (e: any) { message.error(e?.message || '重试失败') }
}
async function handleDelete(record: DeploymentItem) {
  try {
    await deleteDeploy(record.id)
    message.success('已删除')
    loadDeployments()
    loadGpuTopology()
  } catch (e: any) { message.error(e?.message || '删除失败') }
}

onMounted(() => {
  loadDeployments()
  loadGpuTopology()
})
</script>
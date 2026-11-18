<template>
  <div class="page-container">
    <!-- 说明条 -->
    <a-alert type="info" show-icon style="margin-bottom:16px">
      <template #message>
        压测会以真实流量打向目标模型。默认<b>直连模型</b>（不经过平台网关，天然不计入 Token 统计）；
        经网关模式会自动打上 <code>X-Perf-Test</code> 标记，网关侧跳过请求日志。
        仅支持对平台自建部署的模型压测。
      </template>
    </a-alert>

    <!-- 统计卡片 -->
    <a-row :gutter="16" style="margin-bottom:16px">
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="累计压测任务" :value="stats.total" :value-style="{ color: '#1890ff' }" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="成功完成" :value="stats.completed" :value-style="{ color: '#52c41a' }" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card size="small">
          <a-statistic title="运行中" :value="stats.running" :value-style="{ color: '#faad14' }" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card size="small">
          <a-statistic
            title="最近 TTFT (P99)"
            :value="stats.latest_ttft_p99_ms ?? '-'"
            suffix="ms"
            :value-style="{ color: '#eb2f96' }"
          />
        </a-card>
      </a-col>
    </a-row>

    <!-- 工具条 -->
    <div class="panel-card">
      <div class="table-toolbar">
        <div class="toolbar-filters">
          <a-select v-model:value="query.status" placeholder="全部状态" allow-clear style="width:130px" @change="loadTasks">
            <a-select-option v-for="(label, key) in statusMap" :key="key" :value="key">{{ label }}</a-select-option>
          </a-select>
          <a-select v-model:value="query.model_id" placeholder="全部模型" allow-clear style="width:190px" @change="loadTasks">
            <a-select-option v-for="m in models" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
          </a-select>
          <a-input-search v-model:value="query.search" placeholder="搜索任务名..." style="width:200px" @search="loadTasks" />
          <a-button @click="reload">刷新</a-button>
        </div>
        <div class="toolbar-actions">
          <a-button :disabled="completedTasks.length < 2" @click="openCompare">
            <template #icon><SwapOutlined /></template>
            历史对比
          </a-button>
          <a-button type="primary" @click="openCreate">
            <template #icon><PlusOutlined /></template>
            新建压测
          </a-button>
        </div>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="panel-card" style="margin-top:16px; padding:0">
      <a-table :data-source="tasks" :loading="loading" row-key="id" :pagination="{ pageSize: 20 }">
        <a-table-column title="任务名称" key="name" width="20%">
          <template #default="{ record }">
            <a style="font-weight:500" @click="openDetail(record)">{{ record.name }}</a>
            <div style="font-size:12px; color:#8c8c8c">{{ record.created_at }}</div>
          </template>
        </a-table-column>
        <a-table-column title="目标模型" key="model" width="14%">
          <template #default="{ record }">
            <a-tag>{{ record.model_name_snapshot || ('模型 #' + record.model_id) }}</a-tag>
            <a-tag v-if="record.via_gateway" color="orange" style="margin-top:4px">经网关</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="模式" key="mode" width="10%">
          <template #default="{ record }">
            <span>{{ modeLabel(record.mode) }}</span>
          </template>
        </a-table-column>
        <a-table-column title="压力参数" key="pressure" width="14%">
          <template #default="{ record }">
            <span style="font-size:12px">{{ pressureText(record) }}</span>
          </template>
        </a-table-column>
        <a-table-column title="状态" key="status" width="16%">
          <template #default="{ record }">
            <a-badge :status="badgeStatus(record.status)" :text="statusMap[record.status] || record.status" />
            <div v-if="record.status === 'running'" style="margin-top:4px">
              <a-progress
                :percent="progressPercent(record)"
                size="small"
                :show-info="false"
                status="active"
              />
              <span style="font-size:11px; color:#8c8c8c">
                {{ record.progress_sent }} / {{ record.progress_total }}
                <template v-if="record.current_rps"> · {{ record.current_rps }} RPS</template>
              </span>
            </div>
            <div v-if="record.error_message" style="font-size:11px; color:#ff4d4f; margin-top:2px">
              {{ shortText(record.error_message, 40) }}
            </div>
          </template>
        </a-table-column>
        <a-table-column title="TTFT (P99)" key="ttft" width="10%">
          <template #default="{ record }">
            <span v-if="record.ttft_p99_ms !== null">{{ record.ttft_p99_ms }} ms</span>
            <span v-else style="color:#d9d9d9">-</span>
          </template>
        </a-table-column>
        <a-table-column title="输出吞吐" key="throughput" width="10%">
          <template #default="{ record }">
            <span v-if="record.output_throughput !== null">{{ record.output_throughput }} tok/s</span>
            <span v-else style="color:#d9d9d9">-</span>
          </template>
        </a-table-column>
        <a-table-column title="操作" key="action" width="16%">
          <template #default="{ record }">
            <a-space wrap>
              <a @click="openDetail(record)">详情</a>
              <a-popconfirm
                v-if="['pending', 'running'].includes(record.status)"
                title="确定中止该压测？"
                @confirm="handleCancel(record)"
              >
                <a style="color:#ff4d4f">中止</a>
              </a-popconfirm>
              <a v-if="record.status === 'completed'" @click="handleDownload(record)">报告</a>
              <a v-if="['completed', 'failed', 'cancelled'].includes(record.status)" @click="handleRerun(record)">重跑</a>
              <a-popconfirm
                v-if="['completed', 'failed', 'cancelled'].includes(record.status)"
                title="确定删除该压测任务？"
                @confirm="handleDelete(record)"
              >
                <a style="color:#ff4d4f">删除</a>
              </a-popconfirm>
            </a-space>
          </template>
        </a-table-column>
      </a-table>
    </div>

    <!-- ============ 新建压测 ============ -->
    <a-modal
      v-model:open="createModal"
      title="新建压测任务"
      :confirm-loading="creating"
      width="760px"
      @ok="handleCreate"
    >
      <!-- 快速模板 -->
      <div style="background:#fafafa; border-radius:8px; padding:12px; border:1px solid #f0f0f0; margin-bottom:16px">
        <span style="font-size:13px; color:#8c8c8c">⚡ 快速模板</span>
        <div style="margin-top:4px">
          <a-tag
            v-for="tpl in templates"
            :key="tpl.label"
            :color="tpl.recommend ? 'blue' : 'default'"
            style="cursor:pointer"
            @click="applyTemplate(tpl)"
          >
            {{ tpl.label }}
          </a-tag>
        </div>
      </div>

      <a-form :model="createForm" layout="vertical">
        <a-divider orientation="left" style="font-size:13px">1. 目标模型</a-divider>
        <a-row :gutter="16">
          <a-col :span="15">
            <a-form-item label="选择模型" required>
              <a-select
                v-model:value="createForm.model_id"
                placeholder="仅列出平台自建部署的模型"
                show-search
                option-filter-prop="label"
              >
                <a-select-option
                  v-for="m in models"
                  :key="m.id"
                  :value="m.id"
                  :label="m.name"
                >
                  {{ m.name }}
                  <span v-if="m.status !== 'online'" style="color:#faad14">（{{ m.status }}）</span>
                  — {{ m.api_base_url }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="9">
            <a-form-item label="任务名称" required>
              <a-input v-model:value="createForm.name" placeholder="如: 7B-GPTQ 标准基准" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="压测打法">
          <a-radio-group v-model:value="createForm.via_gateway">
            <a-radio :value="false">直连模型（推荐，天然不进 Token 统计）</a-radio>
            <a-radio :value="true">经平台网关（测端到端，自动打压测标记）</a-radio>
          </a-radio-group>
        </a-form-item>

        <a-divider orientation="left" style="font-size:13px">2. 压测模式</a-divider>
        <a-form-item>
          <a-radio-group v-model:value="createForm.mode" button-style="solid">
            <a-radio-button value="closed_loop">闭环并发</a-radio-button>
            <a-radio-button value="open_loop">开环限速</a-radio-button>
            <a-radio-button value="sla">SLA 调压</a-radio-button>
            <a-radio-button value="multi_turn">多轮对话</a-radio-button>
          </a-radio-group>
        </a-form-item>

        <!-- 闭环并发 -->
        <a-row v-if="createForm.mode === 'closed_loop'" :gutter="16">
          <a-col :span="8">
            <a-form-item label="并发数" required>
              <a-input-number v-model:value="createForm.parallel" :min="1" :max="500" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="总请求数" required>
              <a-input-number v-model:value="createForm.number" :min="1" :max="50000" :step="100" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="时长上限（秒）">
              <a-input-number v-model:value="createForm.duration_limit" :min="10" :max="7200" style="width:100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <!-- 开环限速 -->
        <a-row v-if="createForm.mode === 'open_loop'" :gutter="16">
          <a-col :span="8">
            <a-form-item label="目标 RPS" required>
              <a-input-number v-model:value="createForm.rate" :min="0.1" :step="1" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="总请求数" required>
              <a-input-number v-model:value="createForm.number" :min="1" :max="50000" :step="100" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="并发上限">
              <a-input-number v-model:value="createForm.max_concurrency" :min="1" :max="500" style="width:100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <!-- SLA -->
        <div v-if="createForm.mode === 'sla'">
          <a-row :gutter="16">
            <a-col :span="8">
              <a-form-item label="SLA 指标" required>
                <a-select v-model:value="createForm.sla_metric">
                  <a-select-option value="ttft">TTFT（首 token）</a-select-option>
                  <a-select-option value="tpot">TPOT（每 token）</a-select-option>
                  <a-select-option value="latency">端到端延迟</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="阈值（ms）" required>
                <a-input-number v-model:value="createForm.sla_threshold_ms" :min="1" style="width:100%" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="每档请求数">
                <a-input-number v-model:value="createForm.number" :min="1" :max="50000" :step="100" style="width:100%" />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="16">
            <a-col :span="8">
              <a-form-item label="搜索下界（并发）" required>
                <a-input-number v-model:value="createForm.sla_lower_bound" :min="1" :max="500" style="width:100%" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="搜索上界（并发）" required>
                <a-input-number v-model:value="createForm.sla_upper_bound" :min="2" :max="500" style="width:100%" />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="&nbsp;">
                <span style="font-size:12px; color:#8c8c8c">
                  EvalScope 在上下界之间搜索满足 SLA 的最大压力值（非按步长递增）
                </span>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 多轮 -->
        <a-row v-if="createForm.mode === 'multi_turn'" :gutter="16">
          <a-col :span="8">
            <a-form-item label="并发数" required>
              <a-input-number v-model:value="createForm.parallel" :min="1" :max="500" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="对话轮数" required>
              <a-input-number v-model:value="createForm.turns" :min="1" :max="100" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="每轮请求数" required>
              <a-input-number v-model:value="createForm.number" :min="1" :max="50000" :step="50" style="width:100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-divider orientation="left" style="font-size:13px">3. 输入构造</a-divider>
        <a-row :gutter="16">
          <a-col :span="10">
            <a-form-item label="数据集类型">
              <a-select v-model:value="createForm.dataset_type">
                <a-select-option value="random">random（按 token 长度随机生成，推荐）</a-select-option>
                <a-select-option value="openqa">openqa（开放问答）</a-select-option>
                <a-select-option value="speed_benchmark">speed_benchmark（固定 prompt 测速）</a-select-option>
                <a-select-option value="share_gpt">share_gpt（真实对话）</a-select-option>
                <a-select-option value="longalpaca">longalpaca（长上下文）</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="7">
            <a-form-item :label="createForm.dataset_type === 'random' ? '输入长度 (token)' : '输入长度（可选）'">
              <a-input-number v-model:value="createForm.input_length" :min="1" :max="131072" :step="128" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="7">
            <a-form-item :label="createForm.dataset_type === 'random' ? '输出长度 (token)' : '输出长度（可选）'">
              <a-input-number v-model:value="createForm.output_length" :min="1" :max="32768" :step="64" style="width:100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-divider orientation="left" style="font-size:13px">4. 高级设置</a-divider>
        <a-row :gutter="16">
          <a-col :span="6">
            <a-form-item label="stream">
              <a-switch v-model:checked="createForm.stream" checked-children="开" un-checked-children="关" />
              <div style="font-size:11px; color:#8c8c8c">关闭则无法测 TTFT</div>
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item label="temperature">
              <a-input-number v-model:value="createForm.temperature" :min="0" :max="2" :step="0.1" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item label="请求超时（秒）">
              <a-input-number v-model:value="createForm.request_timeout" :min="1" :max="600" style="width:100%" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item label="tokenizer（random 数据集必填）">
              <a-input v-model:value="createForm.tokenizer_path" placeholder="如 Qwen/Qwen2.5-7B-Instruct" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>

    <!-- ============ 结果详情 ============ -->
    <a-modal
      v-model:open="detailModal"
      :title="'压测结果 — ' + detailTitle"
      footer="关闭"
      width="900px"
      @cancel="closeDetail"
    >
      <template v-if="current">
        <!-- 配置回显 -->
        <div style="background:#fafafa; border-radius:8px; padding:10px 14px; margin-bottom:14px; font-size:12.5px">
          <a-tag>{{ modeLabel(current.mode) }}</a-tag>
          <span>{{ pressureText(current) }}</span>
          <span style="margin-left:8px">
            数据集 <b>{{ current.dataset_type }}</b>
            <template v-if="current.input_length"> · {{ current.input_length }} → {{ current.output_length }} token</template>
          </span>
          <span v-if="current.duration_seconds" style="color:#8c8c8c; margin-left:8px">
            （耗时 {{ current.duration_seconds }}s）
          </span>
        </div>

        <!-- 运行中：实时进度 -->
        <div
          v-if="current.status === 'running' || current.status === 'pending'"
          style="margin-bottom:14px"
        >
          <a-progress
            :percent="progressPercent(current)"
            :status="current.status === 'running' ? 'active' : 'normal'"
          />
          <div style="font-size:12px; color:#8c8c8c; margin-top:-4px">
            已处理 {{ current.progress_sent || 0 }} / {{ current.progress_total || '?' }}
            <template v-if="current.current_rps"> · 当前约 {{ current.current_rps }} RPS</template>
            <span style="margin-left:8px; color:#1890ff">（每 3 秒自动刷新）</span>
          </div>
        </div>

        <!-- 指标卡片 -->
        <a-row :gutter="10" style="margin-bottom:16px">
          <a-col :span="6">
            <div style="background:#fafafa; border-radius:8px; padding:12px; text-align:center">
              <div style="font-size:12px; color:#8c8c8c">TTFT 均值</div>
              <div style="font-size:22px; font-weight:700; color:#52c41a">
                {{ fmtNum(current.ttft_mean_ms) }}<span style="font-size:12px"> ms</span>
              </div>
              <div style="font-size:11px; color:#8c8c8c">P99 {{ fmtNum(current.ttft_p99_ms) }} ms</div>
            </div>
          </a-col>
          <a-col :span="6">
            <div style="background:#fafafa; border-radius:8px; padding:12px; text-align:center">
              <div style="font-size:12px; color:#8c8c8c">TPOT</div>
              <div style="font-size:22px; font-weight:700">{{ fmtNum(current.tpot_mean_ms) }}<span style="font-size:12px"> ms</span></div>
              <div style="font-size:11px; color:#8c8c8c">每 token</div>
            </div>
          </a-col>
          <a-col :span="6">
            <div style="background:#fafafa; border-radius:8px; padding:12px; text-align:center">
              <div style="font-size:12px; color:#8c8c8c">输出吞吐</div>
              <div style="font-size:22px; font-weight:700; color:#1890ff">
                {{ fmtNum(current.output_throughput) }}<span style="font-size:12px"> tok/s</span>
              </div>
              <div style="font-size:11px; color:#8c8c8c">请求 {{ fmtNum(current.request_throughput) }} req/s</div>
            </div>
          </a-col>
          <a-col :span="6">
            <div style="background:#fafafa; border-radius:8px; padding:12px; text-align:center">
              <div style="font-size:12px; color:#8c8c8c">成功率</div>
              <div
                style="font-size:22px; font-weight:700"
                :style="{ color: successColor(current.success_rate) }"
              >
                {{ fmtNum(current.success_rate) }}<span style="font-size:12px"> %</span>
              </div>
              <div style="font-size:11px; color:#8c8c8c">
                {{ current.success_count ?? '-' }} / {{ current.progress_total || current.number || '-' }}
              </div>
            </div>
          </a-col>
        </a-row>

        <!-- 延迟分位 -->
        <template v-if="percentileRows.length">
          <div style="font-weight:600; font-size:13px; margin-bottom:8px">延迟分位</div>
          <div v-for="row in percentileRows" :key="row.label" style="display:flex; align-items:center; gap:8px; margin-bottom:6px; font-size:13px">
            <span style="width:60px; color:#595959">{{ row.label }}</span>
            <div style="flex:1; background:#f5f5f5; border-radius:4px; height:16px; overflow:hidden">
              <div :style="{ width: row.percent + '%', height: '100%', background: 'linear-gradient(90deg,#1890ff,#69c0ff)', borderRadius: '4px' }"></div>
            </div>
            <span style="width:90px; text-align:right; color:#595959">{{ row.value }} ms</span>
          </div>
        </template>

        <!-- 错误分布 -->
        <template v-if="errorRows.length">
          <div style="font-weight:600; font-size:13px; margin:16px 0 8px">失败原因分布</div>
          <a-table :data-source="errorRows" :pagination="false" size="small" row-key="message">
            <a-table-column title="错误信息" data-index="message" />
            <a-table-column title="次数" data-index="count" width="100px" />
          </a-table>
        </template>

        <!-- 运行日志 -->
        <div style="font-weight:600; font-size:13px; margin:16px 0 8px">运行日志</div>
        <div style="background:#1a1a2e; color:#d4d4d4; border-radius:8px; padding:14px; font-family:Consolas,monospace; font-size:12.5px; line-height:1.7; max-height:220px; overflow-y:auto">
          <div v-if="!logs.length" style="color:#6a6a8a">暂无日志</div>
          <div v-for="(line, i) in logs" :key="i" style="white-space:pre-wrap">
            <span style="color:#6a9955">{{ shortText(line.created_at, 19) }}</span>
            <span :style="{ color: levelColor(line.level), margin: '0 4px' }">{{ line.level.toUpperCase() }}</span>
            <span>{{ line.message }}</span>
          </div>
        </div>

        <!-- 引擎原始输出（进度条/tokenizer 下载/异常堆栈） -->
        <a-collapse ghost style="margin-top:8px" :bordered="false">
          <a-collapse-panel key="engine" header="引擎原始输出（EvalScope）">
            <div
              v-if="engineLog && engineLog.exists"
              style="background:#1a1a2e; color:#a8b2c1; border-radius:8px; padding:12px; font-family:Consolas,monospace; font-size:12px; line-height:1.6; max-height:260px; overflow:auto; white-space:pre-wrap"
            >{{ engineLog.content }}</div>
            <div v-else style="font-size:12px; color:#8c8c8c">
              {{ engineLog?.hint || '暂无输出' }}
            </div>
          </a-collapse-panel>
        </a-collapse>
      </template>
    </a-modal>

    <!-- ============ 历史对比 ============ -->
    <a-modal
      v-model:open="compareModal"
      title="历史压测对比"
      :confirm-loading="comparing"
      width="960px"
      @ok="handleCompare"
    >
      <a-form layout="vertical">
        <a-form-item label="选择任务（2-4 个已完成任务）" required>
          <a-select
            v-model:value="compareIds"
            mode="multiple"
            placeholder="选择要对比的历史任务"
            :max-tag-count="4"
            style="width:100%"
          >
            <a-select-option v-for="t in completedTasks" :key="t.id" :value="t.id">
              {{ t.name }} · {{ t.created_at }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>

      <template v-if="compareResult">
        <a-alert
          v-if="!compareResult.strictly_comparable"
          type="warning"
          show-icon
          style="margin-bottom:12px"
          :message="'参数不完全一致，指标对比需谨慎：' + compareResult.diff_fields.join('、')"
        />
        <a-alert
          v-else
          type="success"
          show-icon
          style="margin-bottom:12px"
          message="参数完全一致，可严格横向对比"
        />

        <a-table
          :data-source="compareRows"
          :pagination="false"
          size="small"
          row-key="metric"
          bordered
        >
          <a-table-column title="指标" data-index="label" width="150px" fixed="left" />
          <a-table-column
            v-for="(item, idx) in compareResult.items"
            :key="item.task_id"
            :title="item.name"
            width="180px"
          >
            <template #default="{ record }">
              <div>
                <span>{{ record.values[idx] }}</span>
                <span
                  v-if="record.deltas[idx] !== null && idx > 0"
                  :style="{ color: record.deltas[idx] > 0 ? '#ff4d4f' : '#52c41a', marginLeft: '6px', fontSize: '12px' }"
                >
                  {{ record.deltas[idx] > 0 ? '+' : '' }}{{ record.deltas[idx] }}%
                </span>
              </div>
              <div v-if="record.field === 'ttft_mean_ms'" style="font-size:11px; color:#8c8c8c">
                P99 {{ labelsFor(item.task_id) }}
              </div>
            </template>
          </a-table-column>
        </a-table>
      </template>
    </a-modal>
    <!-- 引擎署名（Apache-2.0 合规） -->
    <div style="margin-top:12px; font-size:12px; color:#8c8c8c; text-align:right; line-height:1.8">
      压测引擎
      <a href="https://github.com/modelscope/evalscope" target="_blank" rel="noopener noreferrer">EvalScope</a>
      （Apache-2.0 · © Alibaba ModelScope）
      <br />
      平台侧负责参数编排、进度回写、结果归一化、流量隔离与历史对比
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, SwapOutlined } from '@ant-design/icons-vue'
import {
  getPerfModels,
  getPerfStats,
  getPerfTasks,
  createPerfTask,
  getPerfTaskDetail,
  getPerfLogs,
  cancelPerfTask,
  rerunPerfTask,
  deletePerfTask,
  comparePerfTasks,
  downloadPerfReport,
  getPerfEngineLog,
} from '@/api/perfApi'
import type {
  PerfTaskItem,
  PerfTaskDetail,
  PerfStats,
  PerfTestableModel,
  PerfCompareResult,
} from '@/types/api'
import type { PerfLogItem, PerfEngineLog } from '@/api/perfApi'

const statusMap: Record<string, string> = {
  pending: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已中止',
}

function modeLabel(mode: string): string {
  const map: Record<string, string> = {
    closed_loop: '闭环并发',
    open_loop: '开环限速',
    sla: 'SLA 调压',
    multi_turn: '多轮对话',
  }
  return map[mode] || mode
}

function badgeStatus(s: string): 'default' | 'processing' | 'success' | 'error' | 'warning' {
  const map: Record<string, 'default' | 'processing' | 'success' | 'error' | 'warning'> = {
    pending: 'default',
    running: 'processing',
    completed: 'success',
    failed: 'error',
    cancelled: 'warning',
  }
  return map[s] || 'default'
}

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return String(Number(v).toFixed(2)).replace(/\.?0+$/, '') || '0'
}

function shortText(s: string, n: number): string {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

function successColor(rate: number | null): string {
  if (rate === null || rate === undefined) return '#8c8c8c'
  if (rate >= 99) return '#52c41a'
  if (rate >= 90) return '#faad14'
  return '#ff4d4f'
}

function levelColor(level: string): string {
  const map: Record<string, string> = {
    info: '#569cd6',
    warn: '#dcdcaa',
    error: '#f44747',
    err: '#f44747',
    ok: '#52c41a',
  }
  return map[level] || '#d4d4d4'
}

function pressureText(t: PerfTaskItem): string {
  if (t.mode === 'open_loop') {
    return `${t.rate ?? '-'} RPS · ${t.number ?? '-'} 请求`
  }
  if (t.mode === 'sla') {
    return `${t.sla_metric || '-'} ≤ ${t.sla_threshold_ms ?? '-'}ms · 并发 ${t.sla_lower_bound ?? '-'}~${t.sla_upper_bound ?? '-'}`
  }
  if (t.mode === 'multi_turn') {
    return `并发 ${t.parallel ?? '-'} · ${t.turns ?? '-'} 轮 · 每轮 ${t.number ?? '-'}`
  }
  return `并发 ${t.parallel ?? '-'} · ${t.number ?? '-'} 请求`
}

function progressPercent(t: PerfTaskItem): number {
  if (!t.progress_total || t.progress_total <= 0) return 0
  return Math.min(100, Math.round((t.progress_sent / t.progress_total) * 100))
}

// ---------- 列表 ----------
const loading = ref(false)
const tasks = ref<PerfTaskItem[]>([])
const models = ref<PerfTestableModel[]>([])
const query = reactive<{ status?: string; model_id?: number; search?: string }>({})
const stats = reactive<PerfStats>({ total: 0, completed: 0, running: 0, latest_ttft_p99_ms: null })

const completedTasks = computed<PerfTaskItem[]>(() =>
  tasks.value.filter((t: PerfTaskItem) => t.status === 'completed')
)

async function loadTasks(): Promise<void> {
  loading.value = true
  try {
    const params: { status?: string; model_id?: number; search?: string } = {}
    if (query.status) params.status = query.status
    if (query.model_id) params.model_id = query.model_id
    if (query.search) params.search = query.search
    tasks.value = (await getPerfTasks(params)) as PerfTaskItem[]
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

async function loadStats(): Promise<void> {
  try {
    const s = (await getPerfStats()) as PerfStats
    stats.total = s.total
    stats.completed = s.completed
    stats.running = s.running
    stats.latest_ttft_p99_ms = s.latest_ttft_p99_ms
  } catch {
    /* 统计失败不影响列表 */
  }
}

async function loadModels(): Promise<void> {
  try {
    models.value = (await getPerfModels()) as PerfTestableModel[]
  } catch {
    models.value = []
  }
}

async function reload(): Promise<void> {
  await Promise.all([loadTasks(), loadStats()])
}

// 运行中任务自动刷新
let pollTimer: number | undefined

function ensurePolling(): void {
  const hasRunning = tasks.value.some((t: PerfTaskItem) => t.status === 'running' || t.status === 'pending')
  if (hasRunning && pollTimer === undefined) {
    pollTimer = window.setInterval(() => {
      void reload()
    }, 3000)
  } else if (!hasRunning && pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

// 每次列表变化后重置轮询状态
watch(tasks, () => ensurePolling())

// ---------- 新建 ----------
const createModal = ref(false)
const creating = ref(false)

interface PerfForm {
  name: string
  model_id: number | undefined
  mode: string
  parallel: number | null
  number: number | null
  rate: number | null
  max_concurrency: number | null
  duration_limit: number
  sla_metric: string
  sla_threshold_ms: number | null
  sla_lower_bound: number | null
  sla_upper_bound: number | null
  turns: number | null
  dataset_type: string
  input_length: number | null
  output_length: number | null
  stream: boolean
  temperature: number
  request_timeout: number
  tokenizer_path: string
  via_gateway: boolean
}

const createForm = reactive<PerfForm>({
  name: '',
  model_id: undefined,
  mode: 'closed_loop',
  parallel: 200,
  number: 2000,
  rate: 20,
  max_concurrency: 200,
  duration_limit: 600,
  sla_metric: 'ttft',
  sla_threshold_ms: 500,
  sla_lower_bound: 10,
  sla_upper_bound: 400,
  turns: 5,
  dataset_type: 'random',
  input_length: 1024,
  output_length: 256,
  stream: true,
  temperature: 0,
  request_timeout: 60,
  tokenizer_path: '',
  via_gateway: false,
})

interface PerfTemplate {
  label: string
  mode: string
  parallel: number
  number: number
  recommend: boolean
}

const templates: PerfTemplate[] = [
  { label: '冒烟试跑 50并发', mode: 'closed_loop', parallel: 50, number: 500, recommend: false },
  { label: '标准基准 200并发 ★', mode: 'closed_loop', parallel: 200, number: 2000, recommend: true },
  { label: 'SLA 找拐点', mode: 'sla', parallel: 10, number: 1000, recommend: false },
  { label: '极限压测 500并发', mode: 'closed_loop', parallel: 500, number: 5000, recommend: false },
]

function applyTemplate(tpl: PerfTemplate): void {
  createForm.mode = tpl.mode
  if (tpl.mode === 'sla') {
    createForm.sla_lower_bound = tpl.parallel
    createForm.number = tpl.number
  } else {
    createForm.parallel = tpl.parallel
    createForm.number = tpl.number
  }
}

function openCreate(): void {
  createForm.name = ''
  createForm.model_id = undefined
  createForm.mode = 'closed_loop'
  createForm.tokenizer_path = ''
  createModal.value = true
  if (!models.value.length) void loadModels()
}

// 选中模型后自动带出 tokenizer（优先用模型的 hf_model_id），
// 避免 random 数据集因缺 tokenizer 在服务端报 AssertionError。
watch(
  () => createForm.model_id,
  (id?: number) => {
    if (!id) return
    if (createForm.tokenizer_path.trim()) return
    const picked = models.value.find((m) => m.id === id)
    if (picked && picked.hf_model_id) {
      createForm.tokenizer_path = picked.hf_model_id
    }
  }
)

async function handleCreate(): Promise<void> {
  if (!createForm.model_id) {
    message.warning('请选择目标模型')
    return
  }
  if (!createForm.name.trim()) {
    message.warning('请填写任务名称')
    return
  }

  const payload: Record<string, unknown> = {
    name: createForm.name.trim(),
    model_id: createForm.model_id,
    mode: createForm.mode,
    dataset_type: createForm.dataset_type,
    stream: createForm.stream,
    temperature: createForm.temperature,
    request_timeout: createForm.request_timeout,
    via_gateway: createForm.via_gateway,
    duration_limit: createForm.duration_limit,
  }
  if (createForm.input_length) payload.input_length = createForm.input_length
  if (createForm.output_length) payload.output_length = createForm.output_length
  if (createForm.tokenizer_path.trim()) payload.tokenizer_path = createForm.tokenizer_path.trim()

  if (createForm.mode === 'closed_loop') {
    payload.parallel = createForm.parallel
    payload.number = createForm.number
  } else if (createForm.mode === 'open_loop') {
    payload.rate = createForm.rate
    payload.number = createForm.number
    payload.max_concurrency = createForm.max_concurrency
  } else if (createForm.mode === 'sla') {
    payload.sla_metric = createForm.sla_metric
    payload.sla_threshold_ms = createForm.sla_threshold_ms
    payload.sla_lower_bound = createForm.sla_lower_bound
    payload.sla_upper_bound = createForm.sla_upper_bound
    payload.number = createForm.number
  } else if (createForm.mode === 'multi_turn') {
    payload.parallel = createForm.parallel
    payload.turns = createForm.turns
    payload.number = createForm.number
  }

  creating.value = true
  try {
    await createPerfTask(payload as never)
    message.success('压测任务已提交，可在列表中查看进度')
    createModal.value = false
    await reload()
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : '创建失败')
  } finally {
    creating.value = false
  }
}

// ---------- 详情 ----------
const detailModal = ref(false)
const current = ref<PerfTaskDetail | null>(null)
const detailTitle = ref('')
const logs = ref<PerfLogItem[]>([])
const engineLog = ref<PerfEngineLog | null>(null)

interface PercentileRowView {
  label: string
  value: number | null
  percent: number
}

const percentileRows = computed<PercentileRowView[]>(() => {
  const result = current.value?.result_json as Record<string, any> | null
  const ttft = result?.['percentiles']?.['ttft'] as Record<string, number | null> | undefined
  if (!ttft) return []

  const pairs: Array<{ label: string; value: number | null }> = [
    { label: 'P50', value: ttft['p50'] ?? null },
    { label: 'P90', value: ttft['p90'] ?? null },
    { label: 'P95', value: ttft['p95'] ?? null },
    { label: 'P99', value: ttft['p99'] ?? null },
    { label: 'Max', value: ttft['max'] ?? null },
  ]
  const maxVal = Math.max(...pairs.map((p) => p.value ?? 0), 1)
  return pairs.map((p) => ({
    label: p.label,
    value: p.value,
    percent: Math.round(((p.value ?? 0) / maxVal) * 100),
  }))
})

interface ErrorRowView {
  message: string
  count: number
}

const errorRows = computed<ErrorRowView[]>(() => {
  const result = current.value?.result_json as Record<string, any> | null
  const errors = (result?.['errors'] || {}) as Record<string, number>
  return Object.keys(errors)
    .map((k: string) => ({ message: k, count: Number(errors[k]) }))
    .sort((a: ErrorRowView, b: ErrorRowView) => b.count - a.count)
})

async function refreshDetail(taskId: number): Promise<void> {
  const [detail, logList, engine] = await Promise.all([
    getPerfTaskDetail(taskId),
    getPerfLogs(taskId),
    getPerfEngineLog(taskId, 300),
  ])
  current.value = detail as PerfTaskDetail
  logs.value = logList as PerfLogItem[]
  engineLog.value = engine as PerfEngineLog

  // 任务进入终态 → 停止轮询并刷新列表
  const st = (detail as PerfTaskDetail).status
  if (['completed', 'failed', 'cancelled'].includes(st)) {
    stopDetailPolling()
    void reload()
  }
}

let detailTimer: number | undefined

function stopDetailPolling(): void {
  if (detailTimer !== undefined) {
    window.clearInterval(detailTimer)
    detailTimer = undefined
  }
}

function startDetailPolling(taskId: number): void {
  stopDetailPolling()
  detailTimer = window.setInterval(() => {
    refreshDetail(taskId).catch(() => stopDetailPolling())
  }, 3000)
}

async function openDetail(record: PerfTaskItem): Promise<void> {
  detailTitle.value = record.name
  current.value = record as PerfTaskDetail
  logs.value = []
  engineLog.value = null
  detailModal.value = true
  try {
    await refreshDetail(record.id)
    // 运行中/排队中才需要轮询，历史任务看一次就够
    const st = (current.value as PerfTaskDetail | null)?.status
    if (st === 'running' || st === 'pending') {
      startDetailPolling(record.id)
    }
  } catch {
    /* 详情失败时保留列表里的数据 */
  }
}

function closeDetail(): void {
  stopDetailPolling()
  detailModal.value = false
  current.value = null
  logs.value = []
  engineLog.value = null
}

// ---------- 对比 ----------
const compareModal = ref(false)
const compareIds = ref<number[]>([])
const compareResult = ref<PerfCompareResult | null>(null)
const comparing = ref(false)

interface CompareRow {
  metric: string
  field: string
  label: string
  values: string[]
  deltas: (number | null)[]
}

const compareRows = computed<CompareRow[]>(() => {
  const res = compareResult.value
  if (!res) return []

  const defs: Array<{ label: string; field: keyof (typeof res.items)[0]; unit: string }> = [
    { label: 'TTFT 均值', field: 'ttft_mean_ms', unit: 'ms' },
    { label: 'TTFT P50', field: 'ttft_p50_ms', unit: 'ms' },
    { label: 'TTFT P90', field: 'ttft_p90_ms', unit: 'ms' },
    { label: 'TTFT P99', field: 'ttft_p99_ms', unit: 'ms' },
    { label: 'TPOT', field: 'tpot_mean_ms', unit: 'ms' },
    { label: '输出吞吐', field: 'output_throughput', unit: 'tok/s' },
    { label: '请求吞吐', field: 'request_throughput', unit: 'req/s' },
    { label: '成功率', field: 'success_rate', unit: '%' },
    { label: '耗时', field: 'duration_seconds', unit: 's' },
  ]

  return defs.map((def) => {
    const values = res.items.map((it) => {
      const raw = it[def.field] as number | null | undefined
      return raw === null || raw === undefined ? '-' : `${raw} ${def.unit}`
    })
    const deltaKey = String(def.field)
    return {
      metric: deltaKey,
      field: deltaKey,
      label: def.label,
      values,
      deltas: res.deltas[deltaKey] || res.items.map(() => null),
    }
  })
})

function labelsFor(taskId: number): string {
  const row = compareRows.value.find((r: CompareRow) => r.field === 'ttft_p99_ms')
  if (!row) return '-'
  const idx = (compareResult.value?.items || []).findIndex((it) => it.task_id === taskId)
  return idx >= 0 ? row.values[idx] : '-'
}

function openCompare(): void {
  compareIds.value = []
  compareResult.value = null
  compareModal.value = true
}

async function handleCompare(): Promise<void> {
  if (compareIds.value.length < 2) {
    message.warning('至少选择 2 个任务')
    return
  }
  if (compareIds.value.length > 4) {
    message.warning('最多选择 4 个任务')
    return
  }
  comparing.value = true
  try {
    compareResult.value = (await comparePerfTasks(compareIds.value)) as PerfCompareResult
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : '对比失败')
  } finally {
    comparing.value = false
  }
}

// ---------- 操作 ----------
async function handleCancel(record: PerfTaskItem): Promise<void> {
  try {
    await cancelPerfTask(record.id)
    message.success('已发送中止信号')
    await reload()
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : '中止失败')
  }
}

async function handleRerun(record: PerfTaskItem): Promise<void> {
  try {
    await rerunPerfTask(record.id)
    message.success('已创建重跑任务')
    await reload()
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : '重跑失败')
  }
}

async function handleDelete(record: PerfTaskItem): Promise<void> {
  try {
    await deletePerfTask(record.id)
    message.success('已删除')
    await reload()
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : '删除失败')
  }
}

async function handleDownload(record: PerfTaskItem): Promise<void> {
  try {
    await downloadPerfReport(record.id)
  } catch {
    message.error('报告下载失败（可能报告目录已被清理）')
  }
}

// ---------- 生命周期 ----------
onMounted(async () => {
  await Promise.all([loadModels(), reload()])
})

onBeforeUnmount(() => {
  stopDetailPolling()
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
})
</script>

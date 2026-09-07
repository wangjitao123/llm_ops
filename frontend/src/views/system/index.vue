<template>
  <div class="page-container">
    <a-tabs v-model:activeKey="activeTab">
      <!-- SSO 配置 -->
      <a-tab-pane key="sso" tab="SSO 认证配置">
        <a-card title="SSO 配置" style="max-width: 720px">
          <a-form :model="ssoForm" layout="vertical">
            <a-form-item label="认证协议" required>
              <a-select v-model:value="ssoForm['sso.protocol']">
                <a-select-option value="oauth2">OAuth 2.0</a-select-option>
                <a-select-option value="saml">SAML 2.0</a-select-option>
                <a-select-option value="ldap">LDAP</a-select-option>
                <a-select-option value="cas">CAS</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="授权地址 (Authorize URL)">
              <a-input v-model:value="ssoForm['sso.authorize_url']" placeholder="https://sso.company.com/oauth2/authorize" />
            </a-form-item>
            <a-form-item label="Token 地址 (Token URL)">
              <a-input v-model:value="ssoForm['sso.token_url']" placeholder="https://sso.company.com/oauth2/token" />
            </a-form-item>
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="Client ID">
                  <a-input v-model:value="ssoForm['sso.client_id']" />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="Client Secret">
                  <a-input-password v-model:value="ssoForm['sso.client_secret']" />
                </a-form-item>
              </a-col>
            </a-row>
            <a-form-item label="回调地址 (Redirect URI)">
              <a-input v-model:value="ssoForm['sso.redirect_uri']" placeholder="https://ai-gateway.company.com/auth/callback" />
            </a-form-item>
            <a-button type="primary" :loading="savingSso" @click="saveSsoConfig">保存配置</a-button>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- 预警规则 -->
      <a-tab-pane key="alerts" tab="用量预警">
        <div class="table-toolbar">
          <div></div>
          <a-button type="primary" @click="openAlertModal">
            <template #icon><PlusOutlined /></template>
            新建预警规则
          </a-button>
        </div>
        <a-table :data-source="alertRules" :loading="alertLoading" row-key="id" :pagination="false">
          <a-table-column title="规则名称" data-index="name" key="name" />
          <a-table-column title="指标类型" key="metric_type" width="140">
            <template #default="{ text }">{{ metricTypeText(text) }}</template>
          </a-table-column>
          <a-table-column title="阈值" data-index="threshold_value" key="threshold" width="150">
            <template #default="{ record }">{{ formatThreshold(record) }}</template>
          </a-table-column>
          <a-table-column title="状态" key="enabled" width="80">
            <template #default="{ record }">
              <a-tag :color="record.enabled ? 'success' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="创建时间" data-index="created_at" key="created_at" width="170" />
        </a-table>

        <a-modal v-model:open="alertModalOpen" title="新建预警规则" :confirm-loading="alertSaving" @ok="handleCreateAlert">
          <a-form :model="alertForm" layout="vertical">
            <a-form-item label="规则名称" required>
              <a-input v-model:value="alertForm.name" placeholder="如：日 Token 用量预警" />
            </a-form-item>
            <a-form-item label="指标类型" required>
              <a-select v-model:value="alertForm.metric_type">
                <a-select-option value="daily_token">日 Token 用量</a-select-option>
                <a-select-option value="monthly_token">月 Token 用量</a-select-option>
                <a-select-option value="daily_cost">日费用</a-select-option>
                <a-select-option value="monthly_cost">月费用</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="阈值" required>
              <a-input-number v-model:value="alertForm.threshold_value" :min="1" style="width: 100%" />
            </a-form-item>
            <a-form-item label="警告百分比">
              <a-slider v-model:value="alertForm.warn_at_percent" :min="50" :max="100" :marks="{ 50: '50%', 80: '80%', 100: '100%' }" />
            </a-form-item>
          </a-form>
        </a-modal>
      </a-tab-pane>

      <!-- 审计日志 -->
      <a-tab-pane key="audit" tab="操作审计">
        <a-table :data-source="auditLogs" :loading="auditLoading" row-key="id" :pagination="{ pageSize: 20 }">
          <a-table-column title="用户" data-index="user_id" key="user" width="130" />
          <a-table-column title="操作类型" key="action_type" width="130">
            <template #default="{ text }"><a-tag color="blue">{{ text }}</a-tag></template>
          </a-table-column>
          <a-table-column title="操作详情" data-index="action_detail" key="detail" ellipsis />
          <a-table-column title="对象" key="target" width="160">
            <template #default="{ record }">{{ record.target_type ? `${record.target_type}#${record.target_id}` : '-' }}</template>
          </a-table-column>
          <a-table-column title="IP" data-index="client_ip" key="ip" width="130">
            <template #default="{ text }">{{ text || '-' }}</template>
          </a-table-column>
          <a-table-column title="结果" key="result" width="80">
            <template #default="{ text }">
              <a-tag :color="text === 'success' ? 'success' : 'error'">{{ text }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="时间" data-index="created_at" key="created_at" width="170" />
        </a-table>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import {
  getSystemConfigs, setSystemConfig,
  getAlertRules, createAlertRule,
  getAuditLogs
} from '@/api/systemApi'
import type { AlertRuleItem, AuditLogItem } from '@/api/systemApi'
import { formatTime, formatTokenCount } from '@/utils'

const activeTab = ref('sso')

// SSO
const ssoForm = reactive<Record<string, string>>({})
const savingSso = ref(false)

// Alerts
const alertRules = ref<AlertRuleItem[]>([])
const alertLoading = ref(false)
const alertModalOpen = ref(false)
const alertSaving = ref(false)
const alertForm = reactive({ name: '', metric_type: 'daily_token', threshold_value: 1000000, warn_at_percent: 80 })

// Audit
const auditLogs = ref<AuditLogItem[]>([])
const auditLoading = ref(false)

const metricTypeMap: Record<string, string> = {
  daily_token: '日 Token 用量', monthly_token: '月 Token 用量',
  daily_cost: '日费用', monthly_cost: '月费用'
}
function metricTypeText(t: string) { return metricTypeMap[t] || t }

async function loadSsoConfig() {
  const configs = (await getSystemConfigs('sso')) as Array<{ config_key: string; config_value: string; encrypted: boolean }>
  configs.forEach((c) => {
    // 敏感配置（secret/加密项）不回填明文，避免 Secret 暴露在页面内存与 DOM 中
    if (c.encrypted || c.config_key.includes('secret')) {
      if (c.config_value) {
        ssoForm[c.config_key] = '' // 留空，提示用户已配置
      }
      return
    }
    ssoForm[c.config_key] = c.config_value
  })
}

async function saveSsoConfig() {
  savingSso.value = true
  try {
    for (const [key, value] of Object.entries(ssoForm)) {
      if (!value) continue
      await setSystemConfig({
        config_key: key,
        config_value: value,
        config_group: 'sso',
        encrypted: key.includes('secret') || key.includes('client_id')
      })
    }
    // 保存成功后清空敏感字段的内存值，缩短明文驻留窗口
    Object.keys(ssoForm).forEach((k) => {
      if (k.includes('secret')) ssoForm[k] = ''
    })
    message.success('SSO 配置已保存')
  } catch { message.error('保存失败') } finally { savingSso.value = false }
}

async function loadAlerts() {
  alertLoading.value = true
  try {
    const rules = (await getAlertRules()) as AlertRuleItem[]
    alertRules.value = rules.map((r) => ({ ...r, created_at: formatTime(r.created_at) }))
  } finally { alertLoading.value = false }
}

function openAlertModal() {
  Object.assign(alertForm, { name: '', metric_type: 'daily_token', threshold_value: 1000000, warn_at_percent: 80 })
  alertModalOpen.value = true
}

function formatThreshold(rule: AlertRuleItem) {
  if (rule.metric_type.includes('token')) return formatTokenCount(rule.threshold_value)
  return `¥${rule.threshold_value}`
}

async function handleCreateAlert() {
  if (!alertForm.name || !alertForm.threshold_value) {
    message.warning('请填写完整信息')
    return
  }
  alertSaving.value = true
  try {
    await createAlertRule({ ...alertForm })
    message.success('预警规则已创建')
    alertModalOpen.value = false
    loadAlerts()
  } catch { message.error('创建失败') } finally { alertSaving.value = false }
}

async function loadAuditLogs() {
  auditLoading.value = true
  try {
    const result = (await getAuditLogs({ page: 1, size: 50 })) as any
    auditLogs.value = (result.items || []).map((l: AuditLogItem) => ({ ...l, created_at: formatTime(l.created_at) }))
  } finally { auditLoading.value = false }
}

onMounted(() => {
  loadSsoConfig()
  loadAlerts()
  loadAuditLogs()
})
</script>
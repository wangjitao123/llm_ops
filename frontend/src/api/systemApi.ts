import request from '@/utils/request'

export interface SystemConfigItem {
  config_key: string
  config_value: string
  config_group: string
  description?: string
  encrypted: boolean
}

export interface AlertRuleItem {
  id: number
  name: string
  metric_type: string
  threshold_value: number
  enabled: boolean
  created_at: string
}

export interface AuditLogItem {
  id: number
  user_id: string
  action_type: string
  action_detail: string
  target_type?: string | null
  target_id?: number | null
  client_ip?: string | null
  result: string
  created_at: string
}

export function getSystemConfigs(group = 'sso') {
  return request.get<SystemConfigItem[]>('/v1/system/config', { params: { group } })
}

export function setSystemConfig(data: {
  config_key: string
  config_value: string
  config_group: string
  description?: string
  encrypted?: boolean
}) {
  return request.post('/v1/system/config', data)
}

export function getAlertRules() {
  return request.get<AlertRuleItem[]>('/v1/system/alerts')
}

export function createAlertRule(data: {
  name: string
  metric_type: string
  threshold_value: number
  warn_at_percent?: number
}) {
  return request.post('/v1/system/alerts', data)
}

export function getAuditLogs(params?: { page?: number; size?: number }) {
  return request.get('/v1/system/audit-logs', { params })
}

/** 开发模式直连登录：调用后端签发真实 JWT（仅 ENABLE_DEV_LOGIN=true 时可用） */
export function devLogin(role = 'admin') {
  return request.post<{ token: string; user: { id: string; name: string; role: string; roles: string[] } }>(
    '/v1/system/dev-login',
    { role }
  )
}
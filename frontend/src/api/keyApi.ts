import request from '@/utils/request'
import type { KeyItem, ApplicationItem } from '@/types/api'

export interface KeyQuery {
  status?: string
  page?: number
  size?: number
}

export function getKeyList(params?: KeyQuery) {
  return request.get<KeyItem[]>('/v1/keys', { params })
}

export function createKey(data: {
  name: string
  application_id?: number
  model_ids?: number[]
  qps_limit?: number
  rpm_limit?: number
  rpd_limit?: number
  token_quota?: number
  expires_at?: string
}) {
  return request.post('/v1/keys', data)
}

export function updateKey(id: number, data: Partial<KeyItem>) {
  return request.put(`/v1/keys/${id}`, data)
}

export function deleteKey(id: number) {
  return request.delete(`/v1/keys/${id}`)
}

export function getApplicationList() {
  return request.get<ApplicationItem[]>('/v1/keys/applications')
}

export function createApplication(data: { name: string; description?: string }) {
  return request.post('/v1/keys/applications', data)
}
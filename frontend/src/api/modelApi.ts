import request from '@/utils/request'
import type { ModelItem } from '@/types/api'

export function getModelList(params?: { provider?: string; status?: string }) {
  return request.get<ModelItem[]>('/v1/models', { params })
}

export function getModelDetail(id: number) {
  return request.get<ModelItem>(`/v1/models/${id}`)
}

export function createModel(data: Partial<ModelItem> & { api_key?: string }) {
  return request.post('/v1/models', data)
}

export function updateModel(id: number, data: Partial<ModelItem>) {
  return request.put(`/v1/models/${id}`, data)
}

export function deleteModel(id: number) {
  return request.delete(`/v1/models/${id}`)
}

export function updateModelStatus(id: number, status: string) {
  return request.put(`/v1/models/${id}/status`, { status })
}

export function getModelVersions(id: number) {
  return request.get(`/v1/models/${id}/versions`)
}
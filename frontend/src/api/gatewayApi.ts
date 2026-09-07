import request from '@/utils/request'
import type { RouteRuleItem } from '@/types/api'

export function getRouteList(params?: { status?: string }) {
  return request.get<RouteRuleItem[]>('/v1/gateway/routes', { params })
}

export function createRoute(data: Partial<RouteRuleItem> & { model_targets?: Array<{ model_id: number; weight: number }> }) {
  return request.post('/v1/gateway/routes', data)
}

export function updateRoute(id: number, data: Partial<RouteRuleItem>) {
  return request.put(`/v1/gateway/routes/${id}`, data)
}

export function deleteRoute(id: number) {
  return request.delete(`/v1/gateway/routes/${id}`)
}

export function syncRouteToHigress(id: number) {
  return request.post(`/v1/gateway/routes/${id}/sync`)
}
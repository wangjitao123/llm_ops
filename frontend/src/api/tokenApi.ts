import request from '@/utils/request'
import type { StatsResponse } from '@/types/api'

export function getTokenStats(params: {
  dimension_type: string
  dimension_id?: number
  start_date?: string
  end_date?: string
  granularity?: 'hourly' | 'daily'
}) {
  return request.get<StatsResponse>('/v1/tokens/stats', { params })
}

export function getTokenSummary(params: {
  start_date?: string
  end_date?: string
  dimension_type?: string
}) {
  return request.get('/v1/tokens/summary', { params })
}

export function getCostReport(params: {
  start_date?: string
  end_date?: string
  group_by?: string
}) {
  return request.get('/v1/tokens/cost-report', { params })
}
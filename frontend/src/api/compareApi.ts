import request from '@/utils/request'

export interface EvalModelScore {
  model_id: number
  model_name: string
  scores: Record<string, number>
  total_score: number
}

export interface CompareResult {
  overall_score: number
  models: EvalModelScore[]
  [key: string]: unknown
}

export interface CompareItem {
  id: number
  name: string
  model_ids: number[]
  dimension_weights: Record<string, number>
  status: string
  result?: CompareResult | null
  recommendation?: string | null
  created_at: string
}

export function getCompareList() {
  return request.get<CompareItem[]>('/v1/compare')
}

export function createCompare(data: { name: string; model_ids: number[] }) {
  return request.post('/v1/compare', data)
}

export function getCompareDetail(id: number) {
  return request.get<CompareItem>(`/v1/compare/${id}`)
}
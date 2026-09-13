import request from '@/utils/request'

export interface EvalModelScore {
  model_id: number
  model_name: string
  scores: Record<string, number>
  total_score: number
  scores_need_human?: string[]
  error?: string
  raw?: Record<string, unknown>
}

export interface CompareResult {
  overall_score: number | null
  models: EvalModelScore[]
  errors?: Array<{ model_id: number; error: string }> | null
  [key: string]: unknown
}

export interface CompareItem {
  id: number
  name: string
  model_ids: number[]
  test_prompts?: Array<Array<{ role: string; content: string }>> | null
  dimension_weights: Record<string, number>
  status: string
  result?: CompareResult | null
  recommendation?: string | null
  created_at: string
}

export function getCompareList() {
  return request.get<CompareItem[]>('/v1/compare')
}

export function createCompare(data: {
  name: string
  model_ids: number[]
  test_prompts?: Array<Array<{ role: string; content: string }>>
}) {
  return request.post('/v1/compare', data)
}

export function getCompareDetail(id: number) {
  return request.get<CompareItem>(`/v1/compare/${id}`)
}

export function runEval(id: number) {
  return request.post(`/v1/compare/${id}/run`)
}

export function updateEvalResult(id: number, data: { models: Array<{ model_id: number; scores: Record<string, number> }> }) {
  return request.patch(`/v1/compare/${id}/result`, data)
}
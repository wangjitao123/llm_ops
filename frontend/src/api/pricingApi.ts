import request from '@/utils/request'

export interface PricingItem {
  model_id: number
  model_name?: string
  input_price_per_1k: number
  output_price_per_1k: number
  currency: string
  remark?: string
  updated_at?: string
}

/** 全部计费单价 + 尚未配置价格（按 0 计费）的模型 id 列表 */
export function getPricingList() {
  return request.get<{ items: PricingItem[]; unpriced_model_ids: number[] }>('/v1/pricing')
}

export function savePricing(
  modelId: number,
  data: { input_price_per_1k: number; output_price_per_1k: number; currency?: string; remark?: string }
) {
  return request.put<PricingItem>(`/v1/pricing/${modelId}`, data)
}

export function deletePricing(modelId: number) {
  return request.delete(`/v1/pricing/${modelId}`)
}
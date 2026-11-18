import request from '@/utils/request'
import type { QuantizationTask } from '@/types/api'

export interface QuantizationTaskCreate {
  name: string
  base_model_id?: number | null
  hf_model_id: string
  output_name?: string
  algorithm: string
  weight_bits: number
  activation_bits: number
  group_size: number
  calib_samples: number
  calib_source?: string
  calib_text?: string
  output_path?: string
}

export function getTaskList(status?: string) {
  return request.get<QuantizationTask[]>('/v1/quantization/tasks', {
    params: status ? { status } : {}
  })
}

export function createTask(data: QuantizationTaskCreate) {
  return request.post<QuantizationTask>('/v1/quantization/tasks', data)
}

export function getTaskDetail(id: number) {
  return request.get<QuantizationTask>(`/v1/quantization/tasks/${id}`)
}

export function submitTask(id: number) {
  return request.post(`/v1/quantization/tasks/${id}/submit`)
}

export function cancelTask(id: number) {
  return request.post(`/v1/quantization/tasks/${id}/cancel`)
}

export function retryTask(id: number) {
  return request.post(`/v1/quantization/tasks/${id}/retry`)
}

export function deleteTask(id: number) {
  return request.delete(`/v1/quantization/tasks/${id}`)
}
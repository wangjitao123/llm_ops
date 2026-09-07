import request from '@/utils/request'
import type { FinetuneTaskItem, DatasetItem } from '@/types/api'

export function getFinetuneTaskList(params?: { status?: string }) {
  return request.get<FinetuneTaskItem[]>('/v1/finetune/tasks', { params })
}

export function createFinetuneTask(data: {
  name: string
  base_model_id: number
  dataset_id: number
  val_dataset_id?: number
  hyper_params?: Record<string, unknown>
}) {
  return request.post('/v1/finetune/tasks', data)
}

export function getFinetuneTaskDetail(id: number) {
  return request.get<FinetuneTaskItem>(`/v1/finetune/tasks/${id}`)
}

export function cancelFinetuneTask(id: number) {
  return request.post(`/v1/finetune/tasks/${id}/cancel`)
}

export function getDatasetList() {
  return request.get<DatasetItem[]>('/v1/finetune/datasets')
}

export function createDataset(data: { name: string; format: string; description?: string }) {
  return request.post('/v1/finetune/datasets', data)
}
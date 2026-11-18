import request from '@/utils/request'
import type { DeploymentItem } from '@/types/api'

export interface DeploymentCreate {
  name: string
  deploy_type?: string
  base_model_id?: number | null
  hf_model_id?: string
  endpoint_url: string
  engine?: string
  gpu_count?: number
  gpu_ids?: number[]
  max_concurrency?: number
  max_input_tokens?: number
  system_prompt?: string | null
  temperature?: number
  top_p?: number
  max_tokens?: number
  frequency_penalty?: number
  tools_json?: any[] | null
  web_search_enabled?: boolean
  web_search_config?: any
  env_vars?: any
  auto_register?: boolean
  health_check_enabled?: boolean
}

export function getDeployList(status?: string, deploy_type?: string, search?: string) {
  return request.get<DeploymentItem[]>('/v1/deployments', {
    params: { status, deploy_type, search }
  })
}

export function createDeploy(data: DeploymentCreate) {
  return request.post<DeploymentItem>('/v1/deployments', data)
}

export function getDeployDetail(id: number) {
  return request.get<DeploymentItem>(`/v1/deployments/${id}`)
}

export function updateDeploy(id: number, data: any) {
  return request.put<DeploymentItem>(`/v1/deployments/${id}`, data)
}

export function deleteDeploy(id: number) {
  return request.delete(`/v1/deployments/${id}`)
}

export function startDeploy(id: number) {
  return request.post(`/v1/deployments/${id}/start`)
}

export function stopDeploy(id: number) {
  return request.post(`/v1/deployments/${id}/stop`)
}

export function restartDeploy(id: number) {
  return request.post(`/v1/deployments/${id}/restart`)
}

export function getQuantizedModels() {
  return request.get('/v1/deployments/quantized-models')
}

export function getGpuTopology() {
  return request.get('/v1/deployments/gpu-topology')
}
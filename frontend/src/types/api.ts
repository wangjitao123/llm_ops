// Common API types

export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export interface PageQuery {
  page?: number
  size?: number
}

// Model types
export interface ModelItem {
  id: number
  name: string
  provider: string
  version: string
  api_base_url: string
  qps_limit: number
  timeout_ms: number
  weight: number
  status: 'online' | 'offline' | 'high_latency' | 'pending'
  health_check_url?: string | null
  model_config?: Record<string, unknown> | null
  description?: string | null
  created_by: string
  created_at: string
  updated_at: string
}

// Key types
export interface KeyItem {
  id: number
  name: string
  key_prefix: string
  key_full?: string
  application_id?: number | null
  model_ids?: number[]
  qps_limit?: number | null
  rpm_limit?: number | null
  rpd_limit?: number | null
  token_quota?: number | null
  token_used: number
  expires_at?: string | null
  status: 'active' | 'disabled' | 'expired' | 'revoked'
  last_used_at?: string | null
  created_at: string
  updated_at: string
}

export interface ApplicationItem {
  id: number
  name: string
  description?: string | null
  created_at: string
}

// Token stats types
export interface StatsPoint {
  date: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  request_count: number
  cost: number
}

export interface StatsResponse {
  dimension_type: string
  dimension_id?: number | null
  points: StatsPoint[]
  total_tokens: number
  total_cost: number
}

// Gateway types
export interface RouteRuleItem {
  id: number
  name: string
  path_pattern: string
  match_type: 'exact' | 'prefix' | 'regex'
  strategy: 'weighted' | 'active_standby' | 'single'
  status: 'enabled' | 'disabled'
  priority: number
  model_targets: Array<{ model_id: number; weight: number; priority: number }>
  created_at: string
  updated_at: string
}

// Finetune types
export interface FinetuneTaskItem {
  id: number
  name: string
  base_model_id: number
  dataset_id: number
  hyper_params: Record<string, unknown>
  status: string
  progress: number
  loss_value?: number | null
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface DatasetItem {
  id: number
  name: string
  format: string
  sample_count: number
  file_size: number
  version: string
  annotation_status: string
  description?: string | null
  created_by: string
  created_at: string
}
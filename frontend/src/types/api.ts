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

// Quantization types
export interface QuantizationTask {
  id: number
  name: string
  base_model_id: number | null
  hf_model_id: string
  output_name: string | null
  algorithm: string
  weight_bits: number
  activation_bits: number
  group_size: number
  calib_samples: number
  calib_source: string
  calib_text: string | null
  output_path: string | null
  status: string
  progress: number
  error_message: string | null
  result_model_id: number | null
  created_by: string
  created_at: string
  updated_at: string
}

// Deployment types
export interface DeploymentItem {
  id: number
  name: string
  deploy_type: string
  status: string
  base_model_id: number | null
  hf_model_id: string | null
  endpoint_url: string
  engine: string | null
  gpu_ids: number[] | null
  gpu_count: number
  gpu_memory_gb: number | null
  max_concurrency: number
  max_input_tokens: number
  system_prompt: string | null
  temperature: number | null
  top_p: number | null
  max_tokens: number
  frequency_penalty: number | null
  tools_json: any[] | null
  web_search_enabled: boolean
  web_search_config: any | null
  env_vars: any | null
  auto_register: boolean
  health_check_enabled: boolean
  error_message: string | null
  health_rate?: number
  created_by: string
  created_at: string
  updated_at: string
}

// ===== 模型压测 =====
export interface PerfTaskItem {
  id: number
  name: string
  model_id: number | null
  model_name_snapshot: string | null
  status: string
  mode: string

  parallel: number | null
  number: number | null
  rate: number | null
  max_concurrency: number | null
  duration_limit: number | null

  sla_metric: string | null
  sla_threshold_ms: number | null
  sla_lower_bound: number | null
  sla_upper_bound: number | null

  turns: number | null

  dataset_type: string
  input_length: number | null
  output_length: number | null
  dataset_file: string | null

  stream: boolean
  temperature: number | null
  request_timeout: number
  tokenizer_path: string | null

  target_url: string | null
  via_gateway: boolean
  fingerprint: string | null

  progress_sent: number
  progress_total: number
  current_rps: number | null

  ttft_mean_ms: number | null
  ttft_p99_ms: number | null
  tpot_mean_ms: number | null
  output_throughput: number | null
  request_throughput: number | null
  success_rate: number | null
  success_count: number | null

  error_message: string | null
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null

  created_by: string
  created_at: string
  updated_at: string
}

/** 详情：额外带全量结果与参数快照 */
export interface PerfTaskDetail extends PerfTaskItem {
  result_json: Record<string, any> | null
  params_json: Record<string, any> | null
}

export interface PerfStats {
  total: number
  completed: number
  running: number
  latest_ttft_p99_ms: number | null
}

export interface PerfTestableModel {
  id: number
  name: string
  provider: string
  status: string
  api_base_url: string
  hf_model_id: string | null
}

export interface PerfCompareItem {
  task_id: number
  name: string
  created_at: string
  mode: string
  model_name: string | null
  parallel: number | null
  rate: number | null
  number: number | null
  dataset_type: string
  input_length: number | null
  output_length: number | null
  stream: boolean
  fingerprint: string | null

  ttft_mean_ms: number | null
  ttft_p50_ms: number | null
  ttft_p90_ms: number | null
  ttft_p99_ms: number | null
  tpot_mean_ms: number | null
  output_throughput: number | null
  request_throughput: number | null
  success_rate: number | null
  duration_seconds: number | null
}

export interface PerfCompareResult {
  items: PerfCompareItem[]
  strictly_comparable: boolean
  diff_fields: string[]
  deltas: Record<string, (number | null)[]>
}
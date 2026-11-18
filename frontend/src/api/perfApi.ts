import request from '@/utils/request'
import type {
  PerfTaskItem,
  PerfTaskDetail,
  PerfStats,
  PerfTestableModel,
  PerfCompareResult,
} from '@/types/api'

export interface PerfTaskCreate {
  name: string
  model_id: number
  mode: string
  parallel?: number | null
  number?: number | null
  rate?: number | null
  max_concurrency?: number | null
  duration_limit?: number
  sla_metric?: string | null
  sla_threshold_ms?: number | null
  sla_lower_bound?: number | null
  sla_upper_bound?: number | null
  turns?: number | null
  dataset_type?: string
  input_length?: number | null
  output_length?: number | null
  dataset_file?: string | null
  stream?: boolean
  temperature?: number
  request_timeout?: number
  tokenizer_path?: string | null
  via_gateway?: boolean
}

export interface PerfLogItem {
  level: string
  message: string
  created_at: string
}

/** 可压测模型（后端已过滤为 provider 以 local- 开头的自建模型） */
export function getPerfModels() {
  return request.get<PerfTestableModel[]>('/v1/perf/models')
}

export function getPerfStats() {
  return request.get<PerfStats>('/v1/perf/stats')
}

export function getPerfTasks(params?: {
  status?: string
  model_id?: number
  search?: string
}) {
  return request.get<PerfTaskItem[]>('/v1/perf/tasks', { params })
}

export function createPerfTask(data: PerfTaskCreate) {
  return request.post<PerfTaskItem>('/v1/perf/tasks', data)
}

export function getPerfTaskDetail(id: number) {
  return request.get<PerfTaskDetail>(`/v1/perf/tasks/${id}`)
}

export function getPerfLogs(id: number) {
  return request.get<PerfLogItem[]>(`/v1/perf/tasks/${id}/logs`)
}

export interface PerfEngineLog {
  exists: boolean
  content: string
  hint?: string
  lines?: number
  size?: number
}

/** 压测子进程的实时输出（EvalScope 进度条 / tokenizer 下载 / 异常堆栈） */
export function getPerfEngineLog(id: number, lines = 200) {
  return request.get<PerfEngineLog>(`/v1/perf/tasks/${id}/engine-log`, {
    params: { lines },
  })
}

export function cancelPerfTask(id: number) {
  return request.post(`/v1/perf/tasks/${id}/cancel`)
}

export function rerunPerfTask(id: number, name?: string) {
  return request.post<PerfTaskItem>(`/v1/perf/tasks/${id}/rerun`, { name: name ?? null })
}

export function deletePerfTask(id: number) {
  return request.delete(`/v1/perf/tasks/${id}`)
}

/** 历史对比：2-4 个已完成任务 */
export function comparePerfTasks(taskIds: number[]) {
  return request.post<PerfCompareResult>('/v1/perf/compare', taskIds)
}

/**
 * 下载 EvalScope 原生 HTML 报告。
 * 走 blob 而不是 window.open —— 需要带 Authorization 头。
 */
export async function downloadPerfReport(id: number): Promise<void> {
  const blob = (await request.instance.get(`/v1/perf/tasks/${id}/report`, {
    responseType: 'blob',
  })) as unknown as Blob
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `perf_report_${id}.html`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

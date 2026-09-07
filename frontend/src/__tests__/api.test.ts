import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the request module used by API layers
vi.mock('@/utils/request', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn()
  }
}))

import request from '@/utils/request'
import * as modelApi from '@/api/modelApi'
import * as keyApi from '@/api/keyApi'
import * as tokenApi from '@/api/tokenApi'
import * as gatewayApi from '@/api/gatewayApi'
import * as finetuneApi from '@/api/finetuneApi'

const mockGet = request.get as ReturnType<typeof vi.fn>
const mockPost = request.post as ReturnType<typeof vi.fn>
const mockPut = request.put as ReturnType<typeof vi.fn>
const mockDelete = request.delete as ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.clearAllMocks()
})

describe('modelApi', () => {
  it('getModelList calls GET /v1/models with params', async () => {
    mockGet.mockResolvedValueOnce([])
    await modelApi.getModelList({ status: 'online' })
    expect(mockGet).toHaveBeenCalledWith('/v1/models', { params: { status: 'online' } })
  })

  it('getModelDetail calls GET with id', async () => {
    await modelApi.getModelDetail(5)
    expect(mockGet).toHaveBeenCalledWith('/v1/models/5')
  })

  it('createModel calls POST with data', async () => {
    const data = { name: 'test', provider: 'deepseek', api_key: 'sk-test' }
    await modelApi.createModel(data)
    expect(mockPost).toHaveBeenCalledWith('/v1/models', data)
  })

  it('updateModelStatus calls PUT status endpoint', async () => {
    await modelApi.updateModelStatus(3, 'offline')
    expect(mockPut).toHaveBeenCalledWith('/v1/models/3/status', { status: 'offline' })
  })
})

describe('keyApi', () => {
  it('createKey calls POST /v1/keys', async () => {
    const data = { name: 'app-key', model_ids: [1, 2] }
    await keyApi.createKey(data)
    expect(mockPost).toHaveBeenCalledWith('/v1/keys', data)
  })

  it('getApplicationList calls GET applications', async () => {
    await keyApi.getApplicationList()
    expect(mockGet).toHaveBeenCalledWith('/v1/keys/applications')
  })

  it('deleteKey calls DELETE with id', async () => {
    await keyApi.deleteKey(10)
    expect(mockDelete).toHaveBeenCalledWith('/v1/keys/10')
  })
})

describe('tokenApi', () => {
  it('getTokenStats calls GET /v1/tokens/stats with params', async () => {
    const params = { dimension_type: 'model' as const, granularity: 'daily' as const }
    await tokenApi.getTokenStats(params)
    expect(mockGet).toHaveBeenCalledWith('/v1/tokens/stats', { params })
  })

  it('getCostReport calls GET /v1/tokens/cost-report', async () => {
    const params = { start_date: '2025-01-01', end_date: '2025-01-31', group_by: 'model' }
    await tokenApi.getCostReport(params)
    expect(mockGet).toHaveBeenCalledWith('/v1/tokens/cost-report', { params })
  })
})

describe('gatewayApi', () => {
  it('getRouteList calls GET /v1/gateway/routes', async () => {
    await gatewayApi.getRouteList()
    expect(mockGet).toHaveBeenCalledWith('/v1/gateway/routes', { params: undefined })
  })

  it('syncRouteToHigress calls POST sync endpoint', async () => {
    await gatewayApi.syncRouteToHigress(7)
    expect(mockPost).toHaveBeenCalledWith('/v1/gateway/routes/7/sync')
  })
})

describe('finetuneApi', () => {
  it('getFinetuneTaskList calls GET tasks', async () => {
    await finetuneApi.getFinetuneTaskList({ status: 'running' })
    expect(mockGet).toHaveBeenCalledWith('/v1/finetune/tasks', { params: { status: 'running' } })
  })

  it('cancelFinetuneTask calls POST cancel', async () => {
    await finetuneApi.cancelFinetuneTask(2)
    expect(mockPost).toHaveBeenCalledWith('/v1/finetune/tasks/2/cancel')
  })
})
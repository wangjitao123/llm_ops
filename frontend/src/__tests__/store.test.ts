import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia, type Pinia } from 'pinia'

// ============================================================
// userStore unit tests
// ============================================================

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = String(v) },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { store = {} }
  }
})()

function clearStorages() {
  try { window.sessionStorage.clear() } catch { localStorageMock.clear() }
}

describe('stores/userStore', () => {
  let pinia: Pinia
  let useUserStore: any

  beforeEach(async () => {
    clearStorages()

    // Fresh Pinia per test to avoid cross-test state
    pinia = createPinia()
    setActivePinia(pinia)

    vi.resetModules()
    const module = await import('@/stores/userStore')
    useUserStore = module.useUserStore
  })

  it('initializes with no token and not logged in', () => {
    const store = useUserStore()
    expect(store.token).toBe('')
    expect(store.isLoggedIn).toBe(false)
    expect(store.user).toBeNull()
  })

  it('setToken persists to session storage', () => {
    const store = useUserStore()
    store.setToken('test-token')
    expect(store.token).toBe('test-token')
    expect(store.isLoggedIn).toBe(true)
    expect(window.sessionStorage.getItem('ai_gw_token')).toBe('test-token')
    // 不落 localStorage（防 XSS 持久窃取）
    expect(window.localStorage.getItem('ai_gw_token')).toBeNull()
  })

  it('setUser persists user info', () => {
    const store = useUserStore()
    store.setUser({ id: 'admin', name: '管理员', role: 'admin', roles: ['admin'] })
    expect(store.userName).toBe('管理员')
    expect(store.user?.id).toBe('admin')
    const saved = JSON.parse(window.sessionStorage.getItem('ai_gw_user') as string)
    expect(saved.name).toBe('管理员')
  })

  it('logout clears token and user', () => {
    const store = useUserStore()
    store.setToken('abc')
    store.setUser({ id: 'u1', name: 'User', role: 'dev', roles: [] })
    store.logout()
    expect(store.token).toBe('')
    expect(store.isLoggedIn).toBe(false)
    expect(store.user).toBeNull()
    expect(window.sessionStorage.getItem('ai_gw_token')).toBeNull()
    expect(window.sessionStorage.getItem('ai_gw_user')).toBeNull()
  })
})
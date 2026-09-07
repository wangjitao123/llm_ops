/**
 * 认证令牌存储工具
 *
 * 安全说明（对应 Code Review 🔴 SEC-001）：
 * - 生产环境推荐：令牌由后端写入 httpOnly + Secure + SameSite Cookie，前端不接触令牌，
 *   可彻底杜绝 XSS 窃取。此方案需后端配合（FastAPI 设置 Set-Cookie）。
 * - 过渡方案：本工具将令牌统一收敛到 sessionStorage 并集中管理，相比 localStorage
 *   关闭浏览器即失效，缩短令牌暴露窗口，且便于未来无痛切换为 httpOnly Cookie 方案。
 * - 所有读写令牌的代码必须经由本工具，禁止直接访问 sessionStorage/localStorage。
 */

const TOKEN_KEY = 'ai_gw_token'

/** 令牌存储介质：sessionStorage（会话级）。如需 httpOnly Cookie 方案，替换此实现即可。 */
const storage: Storage = window.sessionStorage

export function getToken(): string {
  return storage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string): void {
  storage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  storage.removeItem(TOKEN_KEY)
}

/** 读取本地缓存的用户信息（非敏感，仅展示用）。 */
export function getUser(): Record<string, unknown> | null {
  const raw = storage.getItem('ai_gw_user')
  if (!raw) return null
  try {
    return JSON.parse(raw) as Record<string, unknown>
  } catch {
    return null
  }
}

export function setUser(user: Record<string, unknown> | null): void {
  if (user) {
    storage.setItem('ai_gw_user', JSON.stringify(user))
  } else {
    storage.removeItem('ai_gw_user')
  }
}

export function clearAuth(): void {
  clearToken()
  setUser(null)
}

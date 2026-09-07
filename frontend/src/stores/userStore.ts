import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getToken, setToken as persistToken, getUser, setUser as persistUser, clearAuth } from '@/utils/auth'

export interface UserInfo {
  id: string
  name: string
  email?: string
  role: string
  roles: string[]
}

export const useUserStore = defineStore('user', () => {
  const user = ref<UserInfo | null>(null)
  const token = ref<string>(getToken())

  const isLoggedIn = computed(() => !!token.value)
  const userName = computed(() => user.value?.name || '')

  function setUser(userInfo: UserInfo | null) {
    user.value = userInfo
    persistUser(userInfo as Record<string, unknown> | null)
  }

  function setToken(newToken: string) {
    token.value = newToken
    persistToken(newToken)
  }

  function loadUser() {
    const cached = getUser() as UserInfo | null
    if (cached) user.value = cached
  }

  function logout() {
    user.value = null
    token.value = ''
    clearAuth()
  }

  return { user, token, isLoggedIn, userName, setUser, setToken, loadUser, logout }
})

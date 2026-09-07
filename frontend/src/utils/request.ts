import axios from 'axios'
import type { AxiosRequestConfig, AxiosInstance } from 'axios'
import { message } from 'ant-design-vue'
import router from '@/router'
import { getToken, clearAuth } from '@/utils/auth'

// 拦截器已在运行时解包 response.data，此处为类型系统补齐对应签名：
// get<T>() 实际返回 Promise<T>（而非 AxiosResponse<T>）。
export interface HttpClient {
  get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  delete<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T>
  patch<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  instance: AxiosInstance
}

const instance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: Number(import.meta.env.VITE_API_TIMEOUT) || 15000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
instance.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor
instance.interceptors.response.use(
  (response) => {
    // Handle wrapped response {code, message, data}
    const res = response.data
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code !== 0 && res.code !== 200) {
        message.error(res.message || '请求失败')
        return Promise.reject(new Error(res.message || 'Error'))
      }
      return res.data
    }
    return res
  },
  (error) => {
    if (error.response?.status === 401) {
      clearAuth()
      // 防止在登录页重复跳转 / 并发 401 触发多次跳转
      if (router.currentRoute.value.path !== '/login') {
        router.replace('/login')
      }
    } else {
      const msg = error.response?.data?.message || error.message || '网络错误'
      message.error(msg)
    }
    return Promise.reject(error)
  }
)

const request = instance as unknown as HttpClient
request.instance = instance

export default request

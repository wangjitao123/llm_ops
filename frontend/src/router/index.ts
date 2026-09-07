import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { getToken } from '@/utils/auth'

// 扩展 meta 类型
declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    icon?: string
    /** 需要的角色；为空则不限制（后端仍会做接口级鉴权） */
    roles?: string[]
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/',
    component: () => import('@/components/layout/BasicLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '总览大屏', icon: 'DashboardOutlined' }
      },
      {
        path: 'models',
        name: 'Models',
        component: () => import('@/views/model/index.vue'),
        meta: { title: '模型管理', icon: 'RobotOutlined' }
      },
      {
        path: 'keys',
        name: 'Keys',
        component: () => import('@/views/key/index.vue'),
        meta: { title: 'Key 管理', icon: 'KeyOutlined' }
      },
      {
        path: 'tokens',
        name: 'Tokens',
        component: () => import('@/views/token/index.vue'),
        meta: { title: 'Token 统计', icon: 'BarChartOutlined' }
      },
      {
        path: 'gateway',
        name: 'Gateway',
        component: () => import('@/views/gateway/index.vue'),
        meta: { title: '统一网关', icon: 'GatewayOutlined', roles: ['admin'] }
      },
      {
        path: 'finetune',
        name: 'Finetune',
        component: () => import('@/views/finetune/index.vue'),
        meta: { title: '模型微调', icon: 'ExperimentOutlined' }
      },
      {
        path: 'compare',
        name: 'Compare',
        component: () => import('@/views/compare/index.vue'),
        meta: { title: '模型对比', icon: 'AreaChartOutlined' }
      },
      {
        path: 'system',
        name: 'System',
        component: () => import('@/views/system/index.vue'),
        meta: { title: '系统管理', icon: 'SettingOutlined', roles: ['admin'] }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  document.title = `${String(to.meta.title || '')} - 大模型监测管理平台`
  const token = getToken()

  if (to.path !== '/login' && !token) {
    next('/login')
    return
  }

  if (to.path === '/login' && token) {
    next('/dashboard')
    return
  }

  // 角色级权限校验（前端粗粒度控制；后端接口级鉴权为最终防线）
  if (to.meta.roles && token) {
    try {
      const raw = sessionStorage.getItem('ai_gw_user')
      if (raw) {
        const user = JSON.parse(raw) as { roles?: string[]; role?: string }
        const hasRole = user.roles?.some((r) => (to.meta.roles as string[]).includes(r))
          || (user.role && (to.meta.roles as string[]).includes(user.role))
        if (!hasRole) {
          next('/dashboard')
          return
        }
      }
    } catch {
      // 用户信息解析失败时不阻塞，交由后端接口鉴权兜底
    }
  }

  next()
})

export default router

<template>
  <a-layout style="min-height: 100vh">
    <!-- 侧边栏（对齐原型：分组导航） -->
    <a-layout-sider v-model:collapsed="collapsed" collapsible :width="220" :style="{ background: '#001529' }" class="app-sider">
      <div class="logo">
        <RobotOutlined class="logo-icon" />
        <span v-if="!collapsed">
          <b>AI 网关</b>
          <small>大模型监测管理平台</small>
        </span>
        <span v-else><RobotOutlined /></span>
      </div>
      <div class="sider-nav">
        <template v-for="group in menuGroups" :key="group.title">
          <div v-if="!collapsed && group.title" class="nav-section-title">{{ group.title }}</div>
          <a-menu
            :selectedKeys="selectedKeys"
            mode="inline"
            theme="dark"
            :style="{ background: '#001529', borderInlineEnd: 'none' }"
            @click="handleMenuClick"
          >
            <a-menu-item v-for="item in group.items" :key="item.path">
              <template #icon><component :is="item.icon" /></template>
              <span>{{ item.title }}</span>
              <span v-if="item.badge && !collapsed" class="nav-badge" :class="item.badgeType">{{ item.badge }}</span>
            </a-menu-item>
          </a-menu>
        </template>
      </div>
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="topbar">
        <h5>{{ currentTitle }}</h5>
        <div class="topbar-right">
          <a-dropdown>
            <span class="user-chip">
              <a-avatar size="small" style="background: #1890ff">{{ (userName || '管')[0] }}</a-avatar>
              <span class="user-name">{{ userName || '未登录' }}</span>
            </span>
            <template #overlay>
              <a-menu @click="handleUserMenu">
                <a-menu-item key="logout"><LogoutOutlined /> 退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>
      <a-layout-content class="content-area">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/userStore'
import {
  DashboardOutlined,
  RobotOutlined,
  KeyOutlined,
  BarChartOutlined,
  GatewayOutlined,
  ExperimentOutlined,
  AreaChartOutlined,
  BulbOutlined,
  CloudUploadOutlined,
  SettingOutlined,
  LogoutOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const collapsed = ref(false)
const selectedKeys = ref<string[]>([route.path])

interface MenuItem { path: string; title: string; icon: any; badge?: string; badgeType?: string }
interface MenuGroup { title: string; items: MenuItem[] }

const menuGroups: MenuGroup[] = [
  {
    title: '',
    items: [
      { path: '/dashboard', title: '总览大屏', icon: DashboardOutlined }
    ]
  },
  {
    title: '核心管理',
    items: [
      { path: '/models', title: '模型管理', icon: RobotOutlined },
      { path: '/keys', title: 'Key 管理', icon: KeyOutlined },
      { path: '/tokens', title: 'Token 统计', icon: BarChartOutlined },
      { path: '/gateway', title: '统一网关', icon: GatewayOutlined }
    ]
  },
  {
    title: '进阶能力',
    items: [
      { path: '/compare', title: '模型对比评估', icon: AreaChartOutlined },
      { path: '/finetune', title: '模型微调', icon: ExperimentOutlined },
      { path: '/quantization', title: '模型量化', icon: BulbOutlined, badge: 'NEW', badgeType: 'info' },
      { path: '/deploy', title: '模型部署', icon: CloudUploadOutlined, badge: 'NEW', badgeType: 'info' },
      { path: '/perf', title: '模型压测', icon: DashboardOutlined, badge: 'NEW', badgeType: 'info' }
    ]
  },
  {
    title: '系统管理',
    items: [
      { path: '/system', title: '系统配置', icon: SettingOutlined }
    ]
  }
]

const currentTitle = computed(() => {
  const flat = menuGroups.flatMap((g) => g.items)
  return flat.find((m) => m.path === route.path)?.title || ''
})

const userName = computed(() => userStore.userName)

function handleMenuClick({ key }: { key: string }) {
  router.push(key)
}

function handleUserMenu({ key }: { key: string }) {
  if (key === 'logout') {
    userStore.logout()
    message.success('已退出登录')
    router.push('/login')
  }
}
</script>

<style scoped>
.logo {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px;
  color: #fff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  overflow: hidden;
  white-space: nowrap;
}
.logo-icon { font-size: 24px; color: #1890ff; flex-shrink: 0; }
.logo b { font-size: 17px; display: block; line-height: 1.1; }
.logo small { font-size: 11px; opacity: 0.6; font-weight: 400; }

.sider-nav { flex: 1; overflow-y: auto; overflow-x: hidden; }
.nav-section-title {
  padding: 14px 20px 4px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: rgba(255, 255, 255, 0.35);
  white-space: nowrap;
}
.nav-badge {
  margin-left: auto;
  font-size: 11px;
  border-radius: 10px;
  padding: 0 7px;
  line-height: 18px;
  background: #52c41a;
  color: #fff;
}
.nav-badge.warn { background: #faad14; }
.nav-badge.info { background: #1890ff; }

/* 顶栏 */
.topbar {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.06);
  line-height: 56px;
}
.topbar h5 { font-size: 16px; font-weight: 600; margin: 0; color: var(--text-heading); }
.topbar-right { display: flex; align-items: center; }
.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.2s;
}
.user-chip:hover { background: #f5f5f5; }
.user-name { font-size: 14px; color: var(--text-main); }

.content-area { padding: 24px; min-height: 280px; }
</style>

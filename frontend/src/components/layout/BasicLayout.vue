<template>
  <a-layout style="min-height: 100vh">
    <a-layout-sider v-model:collapsed="collapsed" collapsible :width="220">
      <div class="logo">
        <span v-if="!collapsed">AI 网关平台</span>
        <span v-else>AI</span>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        mode="inline"
        theme="dark"
        @click="handleMenuClick"
      >
        <a-menu-item v-for="item in menuItems" :key="item.path">
          <component :is="item.icon" />
          <span>{{ item.title }}</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>
    <a-layout>
      <a-layout-header class="header">
        <div class="header-title">{{ currentTitle }}</div>
        <div class="header-right">
          <a-dropdown>
            <a class="user-name" @click.prevent>
              <a-avatar size="small" icon="UserOutlined" />
              <span style="margin-left: 8px">{{ userName || '未登录' }}</span>
            </a>
            <template #overlay>
              <a-menu @click="handleUserMenu">
                <a-menu-item key="logout">
                  <LogoutOutlined />
                  退出登录
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>
      <a-layout-content class="content">
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
  SettingOutlined,
  LogoutOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const collapsed = ref(false)
const selectedKeys = ref<string[]>([route.path])

const menuItems = [
  { path: '/dashboard', title: '总览大屏', icon: DashboardOutlined },
  { path: '/models', title: '模型管理', icon: RobotOutlined },
  { path: '/keys', title: 'Key 管理', icon: KeyOutlined },
  { path: '/tokens', title: 'Token 统计', icon: BarChartOutlined },
  { path: '/gateway', title: '统一网关', icon: GatewayOutlined },
  { path: '/finetune', title: '模型微调', icon: ExperimentOutlined },
  { path: '/compare', title: '模型对比', icon: AreaChartOutlined },
  { path: '/system', title: '系统管理', icon: SettingOutlined }
]

const currentTitle = computed(() => {
  const match = menuItems.find((item) => item.path === route.path)
  return match?.title || ''
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
  justify-content: center;
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.1);
}

.header {
  background: #fff;
  padding: 0 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}

.header-title {
  font-size: 16px;
  font-weight: 600;
}

.user-name {
  color: rgba(0, 0, 0, 0.85);
}

.content {
  margin: 24px;
  min-height: 280px;
}
</style>
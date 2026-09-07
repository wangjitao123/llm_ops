<template>
  <div class="login-container">
    <a-card class="login-card">
      <div class="login-header">
        <h1>大模型监测管理平台</h1>
        <p>企业 AI 基础设施统一管控层</p>
      </div>
      <a-form layout="vertical">
        <a-button type="primary" block size="large" :loading="ssoLoading" @click="handleSSOLogin">
          <template #icon><SafetyCertificateOutlined /></template>
          通过公司 SSO 登录
        </a-button>
        <a-divider>或</a-divider>
        <a-button block size="large" @click="handleDevLogin">开发环境直接进入</a-button>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { SafetyCertificateOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useUserStore } from '@/stores/userStore'

const router = useRouter()
const userStore = useUserStore()
const ssoLoading = ref(false)

async function handleSSOLogin() {
  ssoLoading.value = true
  try {
    // TODO: Redirect to SSO authorize URL from system config
    // In production: window.location.href = `${ssoAuthorizeUrl}?client_id=...&redirect_uri=...`
    // Simulated SSO callback for demo
    userStore.setToken('demo-sso-token')
    userStore.setUser({
      id: 'admin',
      name: '平台管理员',
      role: 'admin',
      roles: ['admin', 'developer']
    })
    message.success('SSO 登录成功')
    router.push('/dashboard')
  } finally {
    ssoLoading.value = false
  }
}

function handleDevLogin() {
  userStore.setToken('dev-token')
  userStore.setUser({
    id: 'dev-admin',
    name: '开发管理员',
    role: 'admin',
    roles: ['admin']
  })
  router.push('/dashboard')
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1677ff 0%, #0e2a4a 100%);
}

.login-card {
  width: 400px;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
}

.login-header h1 {
  font-size: 24px;
  color: #1677ff;
  margin-bottom: 8px;
}

.login-header p {
  color: #999;
  font-size: 14px;
}
</style>
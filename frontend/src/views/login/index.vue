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
import { devLogin } from '@/api/systemApi'

const router = useRouter()
const userStore = useUserStore()
const ssoLoading = ref(false)

async function handleSSOLogin() {
  ssoLoading.value = true
  try {
    // TODO: 对接真实 SSO —— 重定向到 SSO authorize URL，回跳后由 /auth/callback 换取令牌
    // 当前 SSO 未配置时，走开发登录通道获取可用令牌
    const res = await devLogin('admin')
    userStore.setToken(res.token)
    userStore.setUser(res.user)
    message.success('登录成功')
    router.push('/dashboard')
  } catch (e) {
    message.error('登录失败：请确认后端服务已启用 dev-login')
  } finally {
    ssoLoading.value = false
  }
}

async function handleDevLogin() {
  ssoLoading.value = true
  try {
    const res = await devLogin('admin')
    userStore.setToken(res.token)
    userStore.setUser(res.user)
    message.success('开发环境登录成功')
    router.push('/dashboard')
  } catch (e) {
    message.error('开发登录失败：请检查后端 ENABLE_DEV_LOGIN 是否开启')
  } finally {
    ssoLoading.value = false
  }
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
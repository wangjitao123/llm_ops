<template>
  <span class="status-badge" :class="badgeClass">
    <span class="dot" v-if="showDot" />
    {{ text }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    status: string
    showDot?: boolean
    customText?: Record<string, string>
  }>(),
  { showDot: true }
)

// 通用状态 → 文案映射；特殊状态调用方可传 customText 覆盖
const defaultText: Record<string, string> = {
  online: '在线', offline: '离线', high_latency: '高延迟', pending: '待配置',
  active: '启用', disabled: '停用', expired: '已过期', revoked: '已回收',
  enabled: '启用', queued: '排队中', running: '运行中', paused: '已暂停',
  completed: '已完成', failed: '失败', cancelled: '已取消', deployed: '已部署',
  success: '成功', warning: '警告', processing: '处理中',
  pending_label: '待标注', labeling: '标注中', labeled: '已标注',
  reviewing: '审核中', reviewed: '已审核',
}

const text = computed(() => (props.customText && props.customText[props.status]) || defaultText[props.status] || props.status)

// CSS class 直接用 status 值（.status-online 等已在 main.css 定义）
const badgeClass = computed(() => `status-${props.status}`)
</script>

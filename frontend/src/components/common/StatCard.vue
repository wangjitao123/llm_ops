<template>
  <div class="stat-card">
    <div class="stat-icon" :style="{ background: `${color}1a`, color }">
      <component :is="icon" />
    </div>
    <div>
      <div class="stat-value">{{ formatted }}</div>
      <div class="stat-label">{{ label }}</div>
      <div v-if="extra" class="stat-trend" :style="{ color: extraColor || '#8c8c8c' }">{{ extra }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: number | string
    icon: any
    color?: string
    suffix?: string
    precision?: number
    formatter?: (v: number) => string
    extra?: string
    extraColor?: string
  }>(),
  { color: '#1890ff', suffix: '', precision: 0 }
)

const formatted = computed(() => {
  if (props.formatter) return props.formatter(Number(props.value) || 0)
  if (typeof props.value === 'number') {
    return `${props.value.toFixed(props.precision)}${props.suffix}`
  }
  return `${props.value}${props.suffix}`
})
</script>

<style scoped>
.stat-value { white-space: nowrap; }
</style>

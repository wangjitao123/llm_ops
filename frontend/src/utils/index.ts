// Utility functions

export function formatTime(time: string | Date | null | undefined, format = 'YYYY-MM-DD HH:mm:ss'): string {
  if (!time) return '-'
  const date = new Date(time)
  if (isNaN(date.getTime())) return String(time)
  
  const pad = (n: number) => String(n).padStart(2, '0')
  return format
    .replace('YYYY', String(date.getFullYear()))
    .replace('MM', pad(date.getMonth() + 1))
    .replace('DD', pad(date.getDate()))
    .replace('HH', pad(date.getHours()))
    .replace('mm', pad(date.getMinutes()))
    .replace('ss', pad(date.getSeconds()))
}

export function formatTokenCount(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return String(n)
}

export function formatCost(cost: number | string): string {
  const n = Number(cost)
  return `¥${n.toFixed(6)}`
}

export function maskKey(key: string): string {
  if (!key) return ''
  if (key.length <= 10) return key
  return `${key.slice(0, 8)}****${key.slice(-4)}`
}
import { describe, it, expect } from 'vitest'
import { formatTime, formatTokenCount, formatCost, maskKey } from '@/utils'

describe('utils/index', () => {
  describe('formatTime', () => {
    it('returns "-" for null/undefined', () => {
      expect(formatTime(null)).toBe('-')
      expect(formatTime(undefined)).toBe('-')
    })

    it('formats a Date object', () => {
      const date = new Date(2025, 0, 15, 10, 30, 0)
      expect(formatTime(date, 'YYYY-MM-DD')).toBe('2025-01-15')
      expect(formatTime(date)).toBe('2025-01-15 10:30:00')
    })

    it('passes through non-date strings', () => {
      expect(formatTime('not-a-date')).toBe('not-a-date')
    })

    it('formats an ISO date string', () => {
      expect(formatTime('2025-06-01T08:00:00.000Z', 'YYYY-MM-DD HH:mm')).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
    })
  })

  describe('formatTokenCount', () => {
    it('formats numbers below 1000 as-is', () => {
      expect(formatTokenCount(500)).toBe('500')
    })

    it('formats thousands with K', () => {
      expect(formatTokenCount(1500)).toBe('1.5K')
    })

    it('formats millions with M', () => {
      expect(formatTokenCount(2500000)).toBe('2.50M')
    })

    it('formats billions with B', () => {
      expect(formatTokenCount(3200000000)).toBe('3.20B')
    })
  })

  describe('formatCost', () => {
    it('prefixes with currency symbol', () => {
      expect(formatCost(0.15)).toBe('¥0.150000')
    })
  })

  describe('maskKey', () => {
    it('masks a long key', () => {
      const key = 'sk-abcdefghijklmnopqrstuvwxyz123456'
      const masked = maskKey(key)
      expect(masked).not.toContain(key.slice(10, -4))
      expect(masked.startsWith(key.slice(0, 8))).toBe(true)
      expect(masked.endsWith(key.slice(-4))).toBe(true)
    })

    it('returns empty for empty input', () => {
      expect(maskKey('')).toBe('')
    })

    it('returns short keys unchanged', () => {
      expect(maskKey('short')).toBe('short')
    })
  })
})
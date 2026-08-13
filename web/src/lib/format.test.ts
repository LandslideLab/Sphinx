import { describe, it, expect } from 'vitest'
import { timeAgo, fmtClock, fmtDuration, STATUS_LABEL, RISK_COLOR, frameworkLabel } from './format'

describe('format helpers', () => {
  it('timeAgo renders relative times', () => {
    expect(timeAgo(null)).toBe('—')
    expect(timeAgo(new Date().toISOString())).toBe('just now')
    const ago60 = new Date(Date.now() - 60_000).toISOString()
    expect(timeAgo(ago60)).toBe('1m ago')
    const ago2h = new Date(Date.now() - 2 * 3600_000).toISOString()
    expect(timeAgo(ago2h)).toBe('2h ago')
    const ago3d = new Date(Date.now() - 3 * 86_400_000).toISOString()
    expect(timeAgo(ago3d)).toBe('3d ago')
  })

  it('fmtClock returns a locale string or dash', () => {
    expect(fmtClock(null)).toBe('—')
    expect(fmtClock('2026-01-01T00:00:00Z')).toContain('2026')
  })

  it('fmtDuration handles seconds / minutes / hours', () => {
    expect(fmtDuration(null)).toBe('—')
    expect(fmtDuration(42)).toBe('42s')
    expect(fmtDuration(90)).toBe('1m 30s')
    expect(fmtDuration(7300)).toBe('2h 2m')
  })

  it('exposes every status label', () => {
    for (const s of ['pending', 'approved', 'rejected', 'cancelled', 'auto_approved', 'auto_rejected']) {
      expect(STATUS_LABEL[s as keyof typeof STATUS_LABEL]).toBeTruthy()
    }
  })

  it('has a color for every risk level', () => {
    for (const r of ['low', 'medium', 'high', 'critical']) {
      expect(RISK_COLOR[r as keyof typeof RISK_COLOR]).toMatch(/^#[0-9a-f]{6}$/)
    }
  })

  it('frameworkLabel capitalizes', () => {
    expect(frameworkLabel('langgraph')).toBe('Langgraph')
    expect(frameworkLabel('openai')).toBe('Openai')
  })
})

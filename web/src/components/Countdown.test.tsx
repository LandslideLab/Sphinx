import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { Countdown, fmtRemaining } from './Countdown'

describe('Countdown', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('formats remaining time from the SLA deadline', () => {
    const created = '2026-01-01T00:00:00Z'
    render(<Countdown deadlineIso={created} timeoutSeconds={125} />)
    expect(screen.getByText(/2m 5s/)).toBeInTheDocument()
  })

  it('turns danger below 30 seconds', () => {
    const created = '2026-01-01T00:00:00Z'
    render(<Countdown deadlineIso={created} timeoutSeconds={20} />)
    const el = screen.getByTitle(/SLA deadline/)
    expect(el.className).toContain('danger')
  })

  it('ticks down over time', () => {
    const created = '2026-01-01T00:00:00Z'
    render(<Countdown deadlineIso={created} timeoutSeconds={120} />)
    expect(screen.getByText(/2m 0s/)).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(30_000))
    expect(screen.getByText(/1m 30s/)).toBeInTheDocument()
  })
})

describe('fmtRemaining', () => {
  it('formats hours/minutes/seconds', () => {
    expect(fmtRemaining(3_600_000 + 120_000 + 5000)).toBe('1h 2m')
    expect(fmtRemaining(125_000)).toBe('2m 5s')
    expect(fmtRemaining(9000)).toBe('9s')
  })
})

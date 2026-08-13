import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act, renderHook } from '@testing-library/react'
import { ToastProvider, useToast } from './Toast'

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  const renderWithToast = () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => <ToastProvider>{children}</ToastProvider>
    const { result } = renderHook(() => useToast(), { wrapper })
    return result.current
  }

  it('pushes success / error / info toasts', () => {
    const { push } = renderWithToast()
    act(() => push('ticket approved', 'success'))
    act(() => push('something broke', 'error'))
    expect(screen.getAllByRole('status')).toHaveLength(2)
    expect(screen.getByText('ticket approved')).toBeInTheDocument()
    expect(screen.getByText('something broke')).toBeInTheDocument()
  })

  it('auto-dismisses after ~4.2s', () => {
    const { push } = renderWithToast()
    act(() => push('ephemeral', 'info'))
    expect(screen.getAllByRole('status')).toHaveLength(1)
    act(() => vi.advanceTimersByTime(4300))
    expect(screen.queryAllByRole('status')).toHaveLength(0)
  })

  it('defaults to info kind', () => {
    const { push } = renderWithToast()
    act(() => push('plain message'))
    const el = screen.getByText('plain message').closest('.toast-item')
    expect(el?.className).toContain('info')
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { createMockWS } from '../test/setup'
import type { Policy } from '../types'

vi.mock('../lib/api', () => ({
  api: {
    listPolicies: vi.fn(),
    createPolicy: vi.fn(),
    updatePolicy: vi.fn(),
    listRequests: vi.fn(),
    ws: () => createMockWS('ws://localhost/api/ws'),
  },
}))

import { Policies } from './Policies'
import * as apiModule from '../lib/api'

const api = apiModule.api as unknown as {
  listPolicies: ReturnType<typeof vi.fn>
  updatePolicy: ReturnType<typeof vi.fn>
  createPolicy: ReturnType<typeof vi.fn>
}

function makePolicy(over: Partial<Policy> = {}): Policy {
  return {
    id: 'p1',
    name: 'standard-review',
    description: 'Standard human review with SLA escalation',
    risk_levels: ['medium', 'high', 'critical'],
    timeout_seconds: 900,
    on_timeout: 'escalate',
    auto_approve_below_risk: true,
    min_reviewers: 1,
    enabled: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

beforeEach(() => vi.clearAllMocks())

describe('Policies', () => {
  it('renders policies with SLA details', async () => {
    api.listPolicies.mockResolvedValue({ items: [makePolicy()] })
    render(<Policies />)
    expect(await screen.findByText('standard-review')).toBeInTheDocument()
    expect(screen.getByText(/SLA 15m/)).toBeInTheDocument()
    expect(screen.getByText(/escalate on timeout/)).toBeInTheDocument()
  })

  it('marks disabled policies', async () => {
    api.listPolicies.mockResolvedValue({ items: [makePolicy({ enabled: false })] })
    render(<Policies />)
    expect(await screen.findByText('disabled')).toBeInTheDocument()
  })

  it('toggles a policy through updatePolicy', async () => {
    api.listPolicies.mockResolvedValue({ items: [makePolicy()] })
    api.updatePolicy.mockResolvedValue(makePolicy({ enabled: false }))
    render(<Policies />)
    await screen.findByText('standard-review')
    const sw = screen.getByRole('switch')
    fireEvent.click(sw)
    await waitFor(() => {
      expect(api.updatePolicy).toHaveBeenCalledWith('p1', { enabled: false })
    })
  })

  it('creates a new policy through the modal', async () => {
    api.listPolicies.mockResolvedValue({ items: [] })
    api.createPolicy.mockResolvedValue(makePolicy())
    render(<Policies />)
    fireEvent.click(await screen.findByText('+ New policy'))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(withinDialog(dialog, 'New policy').name, { target: { value: 'fast-lane' } })
    fireEvent.click(withinDialog(dialog, 'New policy').save)
    await waitFor(() => {
      expect(api.createPolicy).toHaveBeenCalled()
    })
  })
})

function withinDialog(dialog: HTMLElement, _title: string) {
  return {
    name: dialog.querySelector('input') as HTMLInputElement,
    save: dialog.querySelector('button.btn-primary') as HTMLButtonElement,
  }
}

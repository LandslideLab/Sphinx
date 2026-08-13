import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createMockWS } from '../test/setup'
import type { DecisionLog } from '../types'

vi.mock('../lib/api', () => ({
  api: {
    listDecisions: vi.fn(),
    listRequests: vi.fn(),
    metrics: vi.fn(),
    listPolicies: vi.fn(),
    ws: () => createMockWS('ws://localhost/api/ws'),
  },
}))

import { Decisions } from './Decisions'
import * as apiModule from '../lib/api'

const api = apiModule.api as unknown as { listDecisions: ReturnType<typeof vi.fn> }

function makeLog(over: Partial<DecisionLog> = {}): DecisionLog {
  return {
    id: 'd1',
    request_id: 'r1',
    request_ref: 'REF-A',
    agent_decision: { action: 'refund', amount: 500 },
    human_decision: { action: 'refund', amount: 100 },
    delta: [{ op: 'replace', path: '/amount', from: 500, to: 100 }],
    agreement: false,
    source: 'human_review',
    reviewer_id: 'alice',
    note: 'too much',
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

beforeEach(() => vi.clearAllMocks())

describe('Decisions', () => {
  it('renders decision rows with deltas', async () => {
    api.listDecisions.mockResolvedValue({ total: 1, items: [makeLog()] })
    render(<Decisions />)
    await screen.findByText('REF-A')
    expect(screen.getByText('REF-A')).toBeInTheDocument()
    expect(screen.getByText('alice')).toBeInTheDocument()
    expect(screen.getAllByText(/Human review/).length).toBeGreaterThan(0)
    expect(screen.getByText('✗ corrected')).toBeInTheDocument()
    expect(screen.getByText(/\/amount/)).toBeInTheDocument()
  })

  it('shows agreement when human confirmed', async () => {
    api.listDecisions.mockResolvedValue({
      total: 1,
      items: [makeLog({ delta: null, agreement: true })],
    })
    render(<Decisions />)
    expect(await screen.findByText('✓ agreed')).toBeInTheDocument()
  })

  it('shows empty state', async () => {
    api.listDecisions.mockResolvedValue({ total: 0, items: [] })
    render(<Decisions />)
    expect(await screen.findByText(/No decision records found/)).toBeInTheDocument()
  })

  it('filters by source', async () => {
    api.listDecisions.mockResolvedValue({ total: 0, items: [] })
    render(<Decisions />)
    await screen.findByText(/No decision records found/)
    const combos = screen.getAllByRole('combobox')
    // first combobox is the source filter
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.change(combos[0], { target: { value: 'policy_timeout' } })
    await waitFor(() => {
      expect(api.listDecisions).toHaveBeenCalledWith(expect.objectContaining({ source: 'policy_timeout' }))
    })
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { createMockWS } from '../test/setup'
import type { ApprovalRequest } from '../types'

vi.mock('../lib/api', () => {
  return {
    api: {
      listRequests: vi.fn(),
      getRequest: vi.fn(),
      approve: vi.fn(),
      reject: vi.fn(),
      escalate: vi.fn(),
      cancel: vi.fn(),
      feedback: vi.fn(),
      listPolicies: vi.fn(),
      createPolicy: vi.fn(),
      updatePolicy: vi.fn(),
      listDecisions: vi.fn(),
      metrics: vi.fn(),
      ws: () => createMockWS('ws://localhost/api/ws'),
    },
  }
})

import { Queue } from './Queue'
import * as apiModule from '../lib/api'

const api = apiModule.api as unknown as {
  listRequests: ReturnType<typeof vi.fn>
  approve: ReturnType<typeof vi.fn>
  reject: ReturnType<typeof vi.fn>
  escalate: ReturnType<typeof vi.fn>
}

function makeRequest(over: Partial<ApprovalRequest> = {}): ApprovalRequest {
  return {
    id: 'req-1',
    ref: 'REQ-001',
    session_id: 'sess-1',
    agent_id: 'refund-agent',
    framework: 'langgraph',
    title: 'Approve refund of $300',
    description: 'Refund requested by user',
    action_payload: { action: 'refund', amount: 300 },
    risk_level: 'medium',
    priority: 5,
    status: 'pending',
    requester: 'user-1',
    metadata: { region: 'eu' },
    policy_id: 'p1',
    policy_name: 'standard-review',
    timeout_seconds: 600,
    escalated: false,
    escalated_at: null,
    escalation_note: '',
    reviewer_id: null,
    reviewer_note: '',
    decision_payload: null,
    resolved_by: null,
    outcome: null,
    outcome_note: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    decided_at: null,
    seconds_pending: 0,
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Queue', () => {
  it('renders pending tickets and total count', async () => {
    api.listRequests.mockResolvedValue({ total: 1, items: [makeRequest()] })
    render(<Queue />)
    expect(await screen.findByText('Approve refund of $300')).toBeInTheDocument()
    expect(screen.getByText(/1 ticket/)).toBeInTheDocument()
    expect(screen.getByText('REQ-001')).toBeInTheDocument()
  })

  it('shows empty state when no tickets', async () => {
    api.listRequests.mockResolvedValue({ total: 0, items: [] })
    render(<Queue />)
    expect(await screen.findByText(/No approval requests match/)).toBeInTheDocument()
  })

  it('passes the selected risk filter to the api', async () => {
    api.listRequests.mockResolvedValue({ total: 0, items: [] })
    render(<Queue />)
    await screen.findByText(/No approval requests match/)
    fireEvent.change(screen.getByDisplayValue('All risk levels'), { target: { value: 'critical' } })
    await waitFor(() => {
      expect(api.listRequests).toHaveBeenCalledWith(
        expect.objectContaining({ risk: 'critical' }),
      )
    })
  })

  it('opens the approve modal and calls api.approve', async () => {
    api.listRequests.mockResolvedValue({ total: 1, items: [makeRequest()] })
    api.approve.mockResolvedValue(makeRequest({ status: 'approved' }))
    render(<Queue />)
    await screen.findByText('Approve refund of $300')
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('REQ-001')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve' }))
    await waitFor(() => {
      expect(api.approve).toHaveBeenCalled()
    })
  })

  it('reject calls api.reject with a reviewer note', async () => {
    api.listRequests.mockResolvedValue({ total: 1, items: [makeRequest()] })
    api.reject.mockResolvedValue(makeRequest({ status: 'rejected' }))
    render(<Queue />)
    await screen.findByText('Approve refund of $300')
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByPlaceholderText('Optional note for the audit trail'), { target: { value: 'suspicious' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject' }))
    await waitFor(() => {
      expect(api.reject).toHaveBeenCalledWith('req-1', 'suspicious')
    })
  })

  it('expands the detail panel to reveal metadata', async () => {
    api.listRequests.mockResolvedValue({ total: 1, items: [makeRequest()] })
    render(<Queue />)
    await screen.findByText('Approve refund of $300')
    fireEvent.click(screen.getByLabelText(/Toggle details/))
    expect(await screen.findByText('sess-1')).toBeInTheDocument()
    expect(screen.getByText('"eu"')).toBeInTheDocument()
  })

  it('renders an escalated badge for escalated pending tickets', async () => {
    api.listRequests.mockResolvedValue({ total: 1, items: [makeRequest({ escalated: true, escalation_note: 'manager needs to sign' })] })
    render(<Queue />)
    await screen.findByText(/escalated/)
  })
})

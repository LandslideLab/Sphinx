import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createMockWS } from '../test/setup'
import type { Metrics } from '../types'

vi.mock('../lib/api', () => ({
  api: {
    metrics: vi.fn(),
    listRequests: vi.fn(),
    listDecisions: vi.fn(),
    listPolicies: vi.fn(),
    ws: () => createMockWS('ws://localhost/api/ws'),
  },
}))

import { Metrics as MetricsPage } from './Metrics'
import * as apiModule from '../lib/api'

const api = apiModule.api as unknown as { metrics: ReturnType<typeof vi.fn> }

const sample: Metrics = {
  window: { since_days: null, generated_at: '2026-01-01T00:00:00Z' },
  totals: {
    requests: 28,
    by_status: { pending: 9, approved: 12, auto_approved: 5, rejected: 2 },
    escalated: 3,
    pending: 9,
  },
  governance: {
    escalation_rate: 10.7,
    timeout_rate: 3.6,
    correction_rate: 25,
    reviewer_agreement: 75,
    error_escape_rate: 0,
    sla_compliance_rate: 96.4,
  },
  latency: { human_reviews: 14, avg_seconds: 130, p50_seconds: 90, p95_seconds: 420 },
  risk: {
    low: { created: 8, escalated: 0 },
    medium: { created: 12, escalated: 1 },
    high: { created: 6, escalated: 1 },
    critical: { created: 2, escalated: 1 },
  },
  feedback: { approved_with_feedback: 9, negative_outcomes: 0 },
}

beforeEach(() => vi.clearAllMocks())

describe('Metrics', () => {
  it('renders the four headline stats', async () => {
    api.metrics.mockResolvedValue(sample)
    render(<MetricsPage />)
    expect(await screen.findByText('28')).toBeInTheDocument()
    expect(screen.getByText('Total requests')).toBeInTheDocument()
    expect(screen.getByText('Escalated')).toBeInTheDocument()
    expect(screen.getByText('Human reviews')).toBeInTheDocument()
    expect(screen.getByText(/Avg review latency/)).toBeInTheDocument()
  })

  it('renders all governance gauges with percentages', async () => {
    api.metrics.mockResolvedValue(sample)
    render(<MetricsPage />)
    await screen.findByText('Total requests')
    expect(screen.getByText('Escalation rate')).toBeInTheDocument()
    expect(screen.getByText('SLA compliance')).toBeInTheDocument()
    expect(screen.getAllByText('10.7%').length).toBeGreaterThan(0)
  })

  it('renders the risk breakdown', async () => {
    api.metrics.mockResolvedValue(sample)
    render(<MetricsPage />)
    await screen.findByText('Total requests')
    expect(screen.getByText('Risk breakdown')).toBeInTheDocument()
    expect(screen.getByText('1/12')).toBeInTheDocument() // medium escalated/created
  })

  it('changes window on selection', async () => {
    api.metrics.mockResolvedValue(sample)
    render(<MetricsPage />)
    await screen.findByText('Total requests')
    const { fireEvent, waitFor } = await import('@testing-library/react')
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '7' } })
    await waitFor(() => {
      expect(api.metrics).toHaveBeenCalledWith('7')
    })
  })
})

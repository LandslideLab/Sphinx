import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DeltaView } from './DeltaView'
import type { DecisionLog } from '../types'

const base: DecisionLog = {
  id: 'd1',
  request_id: 'r1',
  request_ref: 'REF-1',
  agent_decision: { action: 'refund', amount: 500 },
  human_decision: null,
  delta: null,
  agreement: null,
  source: 'human_review',
  reviewer_id: 'bob',
  note: '',
  created_at: '2026-01-01T00:00:00Z',
}

describe('DeltaView', () => {
  it('shows a no-delta confirmation when empty', () => {
    render(<DeltaView log={base} />)
    expect(screen.getByText(/no delta/)).toBeInTheDocument()
  })

  it('renders add / remove / replace operations', () => {
    const log: DecisionLog = {
      ...base,
      delta: [
        { op: 'add', path: '/limit', to: 10 },
        { op: 'remove', path: '/legacy', from: true },
        { op: 'replace', path: '/amount', from: 500, to: 200 },
      ],
    }
    const { container } = render(<DeltaView log={log} />)
    const ops = container.querySelectorAll('.op')
    expect(ops).toHaveLength(3)
    expect(ops[0].className).toContain('op-add')
    expect(ops[1].className).toContain('op-remove')
    expect(ops[2].className).toContain('op-replace')
    expect(screen.getByText(/\/amount/)).toBeInTheDocument()
  })
})

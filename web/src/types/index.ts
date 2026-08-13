export type RequestStatus = 'pending' | 'approved' | 'rejected' | 'cancelled' | 'auto_approved' | 'auto_rejected'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'
export type TimeoutAction = 'auto_approve' | 'auto_reject' | 'escalate'
export type DecisionSource = 'human_review' | 'policy_timeout' | 'auto_policy' | 'agent_feedback'

export interface ApprovalRequest {
  id: string
  ref: string
  session_id: string
  agent_id: string
  framework: string
  title: string
  description: string
  action_payload: Record<string, unknown>
  risk_level: RiskLevel
  priority: number
  status: RequestStatus
  requester: string
  metadata: Record<string, unknown>
  policy_id: string | null
  policy_name: string | null
  timeout_seconds: number | null
  escalated: boolean
  escalated_at: string | null
  escalation_note: string
  reviewer_id: string | null
  reviewer_note: string
  decision_payload: Record<string, unknown> | null
  resolved_by: 'human' | 'policy' | 'agent' | null
  outcome: 'success' | 'failure' | 'partial' | null
  outcome_note: string
  created_at: string
  updated_at: string
  decided_at: string | null
  seconds_pending: number
}

export interface DecisionLog {
  id: string
  request_id: string
  request_ref: string | null
  agent_decision: Record<string, unknown>
  human_decision: Record<string, unknown> | null
  delta: { op: string; path: string; from?: unknown; to?: unknown }[] | null
  agreement: boolean | null
  source: DecisionSource
  reviewer_id: string | null
  note: string
  created_at: string
}

export interface Policy {
  id: string
  name: string
  description: string
  risk_levels: RiskLevel[]
  timeout_seconds: number
  on_timeout: TimeoutAction
  auto_approve_below_risk: boolean
  min_reviewers: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface Metrics {
  window: { since_days: number | null; generated_at: string }
  totals: {
    requests: number
    by_status: Record<string, number>
    escalated: number
    pending: number
  }
  governance: {
    escalation_rate: number
    timeout_rate: number
    correction_rate: number
    reviewer_agreement: number
    error_escape_rate: number
    sla_compliance_rate: number
  }
  latency: {
    human_reviews: number
    avg_seconds: number
    p50_seconds: number
    p95_seconds: number
  }
  risk: Record<string, { created: number; escalated: number }>
  feedback: { approved_with_feedback: number; negative_outcomes: number }
}

export interface ListResponse<T> {
  total: number
  items: T[]
}

import type { ApprovalRequest, DecisionLog, ListResponse, Metrics, Policy } from '../types'

const BASE = '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  listRequests: (params: Record<string, string | number | boolean | undefined> = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    }
    return req<ListResponse<ApprovalRequest>>(`/requests?${qs.toString()}`)
  },
  getRequest: (id: string) => req<ApprovalRequest>(`/requests/${id}`),
  approve: (id: string, note = '', decisionPayload?: unknown) =>
    req<ApprovalRequest>(`/requests/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ note, reviewer_id: 'console', decision_payload: decisionPayload, amend: decisionPayload !== undefined }),
    }),
  reject: (id: string, note = '') =>
    req<ApprovalRequest>(`/requests/${id}/reject`, { method: 'POST', body: JSON.stringify({ note, reviewer_id: 'console' }) }),
  escalate: (id: string, note = '') =>
    req<ApprovalRequest>(`/requests/${id}/escalate`, { method: 'POST', body: JSON.stringify({ note, reviewer_id: 'console' }) }),
  cancel: (id: string) => req<ApprovalRequest>(`/requests/${id}/cancel`, { method: 'POST' }),
  feedback: (id: string, outcome: string, note = '') =>
    req<ApprovalRequest>(`/requests/${id}/feedback`, { method: 'POST', body: JSON.stringify({ outcome, note }) }),
  listPolicies: () => req<ListResponse<Policy>>('/policies'),
  createPolicy: (p: Partial<Policy>) => req<Policy>('/policies', { method: 'POST', body: JSON.stringify(p) }),
  updatePolicy: (id: string, p: Partial<Policy>) => req<Policy>(`/policies/${id}`, { method: 'PUT', body: JSON.stringify(p) }),
  listDecisions: (params: Record<string, string | number | boolean | undefined> = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    }
    return req<ListResponse<DecisionLog>>(`/decisions?${qs.toString()}`)
  },
  metrics: (sinceDays?: string) => req<Metrics>(`/metrics${sinceDays ? `?since_days=${sinceDays}` : ''}`),
  ws: () => new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws`),
}

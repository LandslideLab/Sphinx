import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { frameworkLabel, riskBadgeClass, RISK_COLOR, STATUS_LABEL, timeAgo } from '../lib/format'
import type { ApprovalRequest } from '../types'
import { Countdown } from '../components/Countdown'
import { useToast } from '../components/Toast'
import { useLive } from '../lib/useLive'
import { ChevronIcon, ShieldIcon } from '../components/Icons'
import { Payload } from '../components/Payload'

type Action = 'approve' | 'reject' | 'escalate'
type StatusFilter = '' | 'pending' | 'approved' | 'rejected' | 'auto_approved' | 'auto_rejected' | 'cancelled'

export function Queue() {
  const [rows, setRows] = useState<ApprovalRequest[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<StatusFilter>('pending')
  const [framework, setFramework] = useState('')
  const [risk, setRisk] = useState('')
  const [q, setQ] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [modal, setModal] = useState<{ req: ApprovalRequest; action: Action } | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const { push } = useToast()
  const live = useLive(['requests', 'decisions'])

  const load = useCallback(async () => {
    try {
      const d = await api.listRequests({
        status: status || undefined,
        framework: framework || undefined,
        risk: risk || undefined,
        q: q || undefined,
        limit: 100,
      })
      setRows(d.items)
      setTotal(d.total)
    } catch (e) {
      push((e as Error).message, 'error')
    } finally {
      setLoading(false)
    }
  }, [status, framework, risk, q, push])

  useEffect(() => {
    load()
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [load])

  // instant refresh when the live event bus reports a change
  useEffect(() => {
    if (live.revision > 0) load()
  }, [live.revision, load])

  const act = async (req: ApprovalRequest, action: Action, note = '', decisionPayload?: unknown) => {
    setBusyId(req.id)
    try {
      if (action === 'approve') await api.approve(req.id, note, decisionPayload)
      else if (action === 'reject') await api.reject(req.id, note)
      else await api.escalate(req.id, note)
      push(`${req.ref} → ${action}`, 'success')
      setModal(null)
      load()
    } catch (e) {
      push((e as Error).message, 'error')
    } finally {
      setBusyId(null)
    }
  }

  const toggleExpand = (id: string) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))

  return (
    <>
      <div className="topbar">
        <div>
          <h1>Approval Queue</h1>
          <div className="sub">{total} ticket{total === 1 ? '' : 's'} · live via WebSocket event bus · SLA countdown shown for pending requests</div>
        </div>
        <div className="live">
          <span className={`dot${live.live ? ' pulse' : loading ? ' amber' : ''}`} />
          {live.live ? 'live' : loading ? 'syncing' : 'reconnecting'}
        </div>
      </div>

      <div className="filterbar">
        <select value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
          <option value="pending">Pending</option>
          <option value="">All statuses</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="auto_approved">Auto-approved</option>
          <option value="auto_rejected">Auto-rejected</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select value={framework} onChange={(e) => setFramework(e.target.value)}>
          <option value="">All frameworks</option>
          <option value="langgraph">LangGraph</option>
          <option value="openai">OpenAI</option>
          <option value="crewai">CrewAI</option>
          <option value="generic">Generic</option>
        </select>
        <select value={risk} onChange={(e) => setRisk(e.target.value)}>
          <option value="">All risk levels</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>
        <input type="search" placeholder="Search ref / agent / title…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {loading && rows.length === 0 ? (
        <QueueSkeleton />
      ) : rows.length === 0 ? (
        <div className="empty">
          <div className="empty-ico">◫</div>
          <div>No approval requests match the current filters.</div>
          <div className="empty-hint">Try clearing the filters, or create a request from the SDK / MCP tools and watch it land here in real time.</div>
        </div>
      ) : (
        rows.map((r) => (
          <div key={r.id} className={`request-card${r.escalated && r.status === 'pending' ? ' escalated-card' : ''}`}>
            <div className="request-head">
              <span className={`badge ${r.status}`}>{STATUS_LABEL[r.status]}</span>
              <span className={`badge ${riskBadgeClass(r.risk_level)}`}>
                <span className="risk-dot" style={{ background: RISK_COLOR[r.risk_level] }} />
                risk {r.risk_level}
              </span>
              {r.escalated && r.status === 'pending' && <span className="badge escalated">▲ escalated</span>}
              <span className="mono text-faint">{r.ref}</span>
              <span className="request-title">{r.title}</span>
              {r.status === 'pending' && r.timeout_seconds ? (
                <Countdown deadlineIso={r.created_at} timeoutSeconds={r.timeout_seconds} />
              ) : (
                <span className="text-faint small mono">{timeAgo(r.created_at)}</span>
              )}
              <button
                className={`expand-btn${expanded[r.id] ? ' open' : ''}`}
                onClick={() => toggleExpand(r.id)}
                aria-expanded={!!expanded[r.id]}
                aria-label={`Toggle details for ${r.ref}`}
              >
                <ChevronIcon size={15} />
              </button>
            </div>
            {r.description && <div className="request-desc">{r.description}</div>}
            <div className="request-meta">
              <span>agent <b>{r.agent_id}</b></span>
              <span>framework <b>{frameworkLabel(r.framework)}</b></span>
              <span>policy <b>{r.policy_name ?? '—'}</b></span>
              {r.decided_at && <span>decided <b>{timeAgo(r.decided_at)}</b></span>}
              {r.outcome && <span>outcome <b>{r.outcome}</b></span>}
            </div>

            {expanded[r.id] && (
              <div className="detail-panel">
                <div className="detail-item">
                  <div className="k">Session</div>
                  <div className="v">{r.session_id}</div>
                </div>
                <div className="detail-item">
                  <div className="k">Requester</div>
                  <div className="v">{r.requester ?? '—'}</div>
                </div>
                <div className="detail-item">
                  <div className="k">Priority</div>
                  <div className="v">{r.priority}</div>
                </div>
                <div className="detail-item">
                  <div className="k">Reviewer</div>
                  <div className="v">{r.reviewer_id ?? '—'}</div>
                </div>
                <div className="detail-item">
                  <div className="k">Created</div>
                  <div className="v">{new Date(r.created_at).toLocaleString()}</div>
                </div>
                <div className="detail-item">
                  <div className="k">Updated</div>
                  <div className="v">{new Date(r.updated_at).toLocaleString()}</div>
                </div>
                {r.metadata && Object.keys(r.metadata).length > 0 && (
                  <div className="detail-item" style={{ gridColumn: '1 / -1' }}>
                    <div className="k">Metadata</div>
                    <Payload value={r.metadata as Record<string, unknown>} maxHeight={140} />
                  </div>
                )}
              </div>
            )}

            {r.status === 'pending' && (
              <div className="request-actions">
                <button className="btn btn-sm btn-success" disabled={busyId === r.id} onClick={() => setModal({ req: r, action: 'approve' })}>
                  Approve
                </button>
                <button className="btn btn-sm btn-danger" disabled={busyId === r.id} onClick={() => setModal({ req: r, action: 'reject' })}>
                  Reject
                </button>
                <button className="btn btn-sm btn-warn" disabled={busyId === r.id} onClick={() => act(r, 'escalate', 'Escalated from console.')}>
                  Escalate
                </button>
              </div>
            )}
            {r.escalation_note && r.status === 'pending' && (
              <div className="small text-dim mt8">
                <ShieldIcon size={11} /> escalation note: {r.escalation_note}
              </div>
            )}
            <Payload value={r.action_payload} />
          </div>
        ))
      )}

      {modal && (
        <DecideModal
          req={modal.req}
          action={modal.action}
          busy={busyId === modal.req.id}
          onClose={() => setModal(null)}
          onConfirm={(note, payload) => act(modal.req, modal.action, note, payload)}
        />
      )}
    </>
  )
}

function QueueSkeleton() {
  return (
    <div>
      {[0, 1, 2].map((i) => (
        <div key={i} className="card" style={{ marginBottom: 14, padding: 18 }}>
          <div className="skeleton" style={{ height: 16, width: '45%', marginBottom: 10 }} />
          <div className="skeleton" style={{ height: 12, width: '80%', marginBottom: 8 }} />
          <div className="skeleton" style={{ height: 12, width: '60%' }} />
        </div>
      ))}
    </div>
  )
}

function DecideModal({ req, action, busy, onClose, onConfirm }: {
  req: ApprovalRequest
  action: Action
  busy: boolean
  onClose: () => void
  onConfirm: (note: string, payload?: unknown) => void
}) {
  const [note, setNote] = useState('')
  const [payload, setPayload] = useState(JSON.stringify(req.action_payload, null, 2))
  const [amend, setAmend] = useState(false)
  const [payloadError, setPayloadError] = useState<string | null>(null)

  const confirm = () => {
    let parsed: unknown
    if (amend) {
      try {
        parsed = JSON.parse(payload)
      } catch {
        setPayloadError('Invalid JSON — fix or uncheck "amend decision payload".')
        return
      }
    }
    onConfirm(note, amend ? parsed : undefined)
  }

  const verb = action === 'approve' ? 'Approve' : action === 'reject' ? 'Reject' : 'Escalate'
  const cls = action === 'approve' ? 'btn-success' : action === 'reject' ? 'btn-danger' : 'btn-warn'

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={`${verb} ${req.ref}`} onClick={(e) => e.stopPropagation()}>
        <h3>{verb}</h3>
        <div className="modal-sub">
          <span className={`badge ${req.status}`}>{req.ref}</span>{' '}
          <span className={`badge ${riskBadgeClass(req.risk_level)}`}>{req.title}</span>
        </div>
        <div className="field">
          <label>Reviewer note (recorded in decision log)</label>
          <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note for the audit trail" />
        </div>
        {action === 'approve' && (
          <>
            <label className="small text-dim" style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8 }}>
              <input type="checkbox" checked={amend} onChange={(e) => setAmend(e.target.checked)} />
              Amend decision payload (records human↔agent delta)
            </label>
            {amend && (
              <div className="field">
                <textarea rows={7} className="mono" value={payload} onChange={(e) => setPayload(e.target.value)} />
                {payloadError && <div className="small" style={{ color: 'var(--red)' }}>{payloadError}</div>}
              </div>
            )}
          </>
        )}
        <div className="modal-actions">
          <button className="btn btn-sm btn-ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className={`btn btn-sm ${cls}`} disabled={busy} onClick={confirm}>
            {busy ? 'Working…' : verb}
          </button>
        </div>
      </div>
    </div>
  )
}

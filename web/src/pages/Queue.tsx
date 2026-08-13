import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { frameworkLabel, riskBadgeClass, STATUS_LABEL, timeAgo } from '../lib/format'
import type { ApprovalRequest } from '../types'
import { Countdown } from '../components/Countdown'
import { useToast } from '../components/Toast'

type Action = 'approve' | 'reject' | 'escalate'

export function Queue() {
  const [rows, setRows] = useState<ApprovalRequest[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState('pending')
  const [framework, setFramework] = useState('')
  const [q, setQ] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [modal, setModal] = useState<{ req: ApprovalRequest; action: Action } | null>(null)
  const { push } = useToast()

  const load = useCallback(async () => {
    try {
      const d = await api.listRequests({ status: status || undefined, framework: framework || undefined, q: q || undefined, limit: 100 })
      setRows(d.items)
      setTotal(d.total)
    } catch (e) {
      push((e as Error).message, 'error')
    } finally {
      setLoading(false)
    }
  }, [status, framework, q, push])

  useEffect(() => {
    load()
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [load])

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

  return (
    <>
      <div className="topbar">
        <div>
          <h1>Approval Queue</h1>
          <div className="sub">{total} ticket{total === 1 ? '' : 's'} · polled live · SLA countdown shown for pending</div>
        </div>
        <div className="live"><span className={loading ? 'dot amber' : 'dot'} /> {loading ? 'syncing' : 'live'}</div>
      </div>

      <div className="filterbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
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
        <input type="search" placeholder="Search ref / agent / title…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {loading && rows.length === 0 ? (
        <div className="empty"><span className="spinner" /> loading…</div>
      ) : rows.length === 0 ? (
        <div className="empty">No approval requests match the current filters.</div>
      ) : (
        rows.map((r) => (
          <div key={r.id} className={`request-card${r.escalated && r.status === 'pending' ? ' escalated-card' : ''}`}>
            <div className="request-head">
              <span className={`badge ${r.status}`}>{STATUS_LABEL[r.status]}</span>
              <span className={`badge ${riskBadgeClass(r.risk_level)}`}>risk {r.risk_level}</span>
              {r.escalated && r.status === 'pending' && <span className="badge escalated">▲ escalated</span>}
              <span className="mono text-faint">{r.ref}</span>
              <span className="request-title">{r.title}</span>
              {r.status === 'pending' && r.timeout_seconds ? (
                <Countdown deadlineIso={r.created_at} timeoutSeconds={r.timeout_seconds} />
              ) : (
                <span className="text-faint small mono">{timeAgo(r.created_at)}</span>
              )}
            </div>
            {r.description && <div className="request-desc">{r.description}</div>}
            <div className="request-meta">
              <span>agent: {r.agent_id}</span>
              <span>framework: {frameworkLabel(r.framework)}</span>
              <span>policy: {r.policy_name ?? '—'}</span>
              {r.decided_at && <span>decided {timeAgo(r.decided_at)}</span>}
              {r.outcome && <span>outcome: {r.outcome}</span>}
            </div>
            <div className="payload">{JSON.stringify(r.action_payload, null, 2)}</div>
            {r.status === 'pending' && (
              <div className="request-actions">
                <button className="btn-sm btn-success" disabled={busyId === r.id} onClick={() => setModal({ req: r, action: 'approve' })}>
                  Approve
                </button>
                <button className="btn-sm btn-danger" disabled={busyId === r.id} onClick={() => setModal({ req: r, action: 'reject' })}>
                  Reject
                </button>
                <button className="btn-sm btn-warn" disabled={busyId === r.id} onClick={() => act(r, 'escalate', 'Escalated from console.')}>
                  Escalate
                </button>
              </div>
            )}
            {r.escalation_note && r.status === 'pending' && (
              <div className="small text-dim mt8">escalation note: {r.escalation_note}</div>
            )}
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

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{action === 'approve' ? 'Approve' : action === 'reject' ? 'Reject' : 'Escalate'} · {req.ref}</h3>
        <div className="request-desc" style={{ marginBottom: 12 }}>{req.title}</div>
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
          <button className="btn-sm" onClick={onClose} disabled={busy}>Cancel</button>
          <button
            className={`btn-sm ${action === 'approve' ? 'btn-success' : action === 'reject' ? 'btn-danger' : 'btn-warn'}`}
            disabled={busy}
            onClick={confirm}
          >
            {busy ? '…' : action === 'approve' ? 'Approve' : action === 'reject' ? 'Reject' : 'Escalate'}
          </button>
        </div>
      </div>
    </div>
  )
}

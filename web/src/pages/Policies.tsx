import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { fmtDuration } from '../lib/format'
import type { Policy } from '../types'
import { useToast } from '../components/Toast'

const TIMEOUT_ACTION_LABEL: Record<string, string> = {
  auto_approve: 'auto-approve on timeout',
  auto_reject: 'auto-reject on timeout',
  escalate: 'escalate on timeout',
}

export function Policies() {
  const [rows, setRows] = useState<Policy[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<Partial<Policy> | null>(null)
  const { push } = useToast()

  const load = useCallback(async () => {
    const d = await api.listPolicies()
    setRows(d.items)
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    if (!editing) return
    try {
      if (editing.id) await api.updatePolicy(editing.id, editing)
      else await api.createPolicy(editing)
      push('Policy saved', 'success')
      setEditing(null)
      load()
    } catch (e) {
      push((e as Error).message, 'error')
    }
  }

  const toggle = async (p: Policy) => {
    await api.updatePolicy(p.id, { enabled: !p.enabled })
    load()
  }

  return (
    <>
      <div className="topbar">
        <div>
          <h1>SLA Policies</h1>
          <div className="sub">Timeout auto-degradation rules — the anti-approval-fatigue layer</div>
        </div>
        <button className="btn btn-primary" onClick={() => setEditing({ risk_levels: ['medium'], timeout_seconds: 600, on_timeout: 'escalate', auto_approve_below_risk: true, enabled: true, min_reviewers: 1 })}>
          + New policy
        </button>
      </div>

      {loading ? (
        <div className="empty"><span className="spinner" /> loading…</div>
      ) : (
        <div className="card">
          {rows.map((p) => (
            <div className="policy-row" key={p.id}>
              <div style={{ flex: 1 }}>
                <div className="policy-name">
                  {p.name}
                  {!p.enabled && <span className="badge cancelled" style={{ marginLeft: 8 }}>disabled</span>}
                </div>
                <div className="policy-desc">{p.description}</div>
                <div className="policy-meta">
                  <span>risk: {p.risk_levels.join(', ') || '—'}</span>
                  <span>SLA {fmtDuration(p.timeout_seconds)}</span>
                  <span>{TIMEOUT_ACTION_LABEL[p.on_timeout]}</span>
                  <span>{p.auto_approve_below_risk ? 'auto-approve low risk' : 'all risk reviewed'}</span>
                  <span>reviewers: {p.min_reviewers}</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                <button className="btn-sm" onClick={() => setEditing({ ...p })}>Edit</button>
                <button className="btn-sm" onClick={() => toggle(p)}>{p.enabled ? 'Disable' : 'Enable'}</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <PolicyModal
          policy={editing}
          isNew={!editing.id}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}
    </>
  )
}

function PolicyModal({ policy, isNew, onClose, onSave }: {
  policy: Partial<Policy>
  isNew: boolean
  onClose: () => void
  onSave: () => void
}) {
  const [form, setForm] = useState<Partial<Policy>>(policy)

  const set = <K extends keyof Policy>(k: K, v: Policy[K]) => setForm((f) => ({ ...f, [k]: v }))

  const toggleRisk = (level: string) => {
    const cur = (form.risk_levels ?? []) as string[]
    const next = cur.includes(level) ? cur.filter((r) => r !== level) : [...cur, level]
    set('risk_levels', next as never)
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{isNew ? 'New policy' : `Edit · ${form.name}`}</h3>
        <div className="field">
          <label>Name</label>
          <input value={form.name ?? ''} disabled={!isNew} onChange={(e) => set('name', e.target.value)} />
        </div>
        <div className="field">
          <label>Description</label>
          <textarea rows={2} value={form.description ?? ''} onChange={(e) => set('description', e.target.value)} />
        </div>
        <div className="field">
          <label>Applies to risk levels</label>
          <div style={{ display: 'flex', gap: 8 }}>
            {['low', 'medium', 'high', 'critical'].map((r) => (
              <label key={r} className="small" style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <input type="checkbox" checked={(form.risk_levels ?? []).includes(r as never)} onChange={() => toggleRisk(r)} />
                {r}
              </label>
            ))}
          </div>
        </div>
        <div className="field">
          <label>SLA timeout (seconds)</label>
          <input type="number" min={1} value={form.timeout_seconds ?? 600} onChange={(e) => set('timeout_seconds', Number(e.target.value))} />
        </div>
        <div className="field">
          <label>On timeout</label>
          <select value={form.on_timeout ?? 'escalate'} onChange={(e) => set('on_timeout', e.target.value as Policy['on_timeout'])}>
            <option value="auto_approve">Auto-approve</option>
            <option value="auto_reject">Auto-reject</option>
            <option value="escalate">Escalate</option>
          </select>
        </div>
        <div className="field">
          <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={!!form.auto_approve_below_risk} onChange={(e) => set('auto_approve_below_risk', e.target.checked)} />
            Auto-approve below-risk actions instantly
          </label>
        </div>
        <div className="field">
          <label>Min reviewers</label>
          <input type="number" min={1} max={10} value={form.min_reviewers ?? 1} onChange={(e) => set('min_reviewers', Number(e.target.value))} />
        </div>
        <div className="modal-actions">
          <button className="btn-sm" onClick={onClose}>Cancel</button>
          <button className="btn-sm btn-primary" onClick={onSave}>Save</button>
        </div>
      </div>
    </div>
  )
}

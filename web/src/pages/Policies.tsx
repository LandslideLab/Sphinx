import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { fmtDuration, RISK_COLOR } from '../lib/format'
import type { Policy, RiskLevel } from '../types'
import { useToast } from '../components/Toast'
import { useLive } from '../lib/useLive'
import { ShieldIcon } from '../components/Icons'

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
  const live = useLive(['policies'])

  const load = useCallback(async () => {
    const d = await api.listPolicies()
    setRows(d.items)
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (live.revision > 0) load()
  }, [live.revision, load])

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
    try {
      await api.updatePolicy(p.id, { enabled: !p.enabled })
      load()
    } catch (e) {
      push((e as Error).message, 'error')
    }
  }

  return (
    <>
      <div className="topbar">
        <div>
          <h1>SLA Policies</h1>
          <div className="sub">Timeout auto-degradation rules — the anti-approval-fatigue layer</div>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setEditing({ risk_levels: ['medium'], timeout_seconds: 600, on_timeout: 'escalate', auto_approve_below_risk: true, enabled: true, min_reviewers: 1 })}
        >
          + New policy
        </button>
      </div>

      {loading ? (
        <div className="card">
          {[0, 1, 2, 3].map((i) => (
            <div className="skeleton" key={i} style={{ height: 44, marginBottom: 16 }} />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="empty">
          <div className="empty-ico">⚙</div>
          <div>No policies defined yet.</div>
          <div className="empty-hint">Create a policy to control SLA timeouts and auto-degradation behaviour.</div>
        </div>
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
                  <span>
                    {p.risk_levels.map((r: RiskLevel) => (
                      <span key={r} className="risk-dot" style={{ background: RISK_COLOR[r], display: 'inline-block', width: 7, height: 7, borderRadius: '50%', marginRight: 4 }} />
                    ))}
                    risk: {p.risk_levels.join(', ') || '—'}
                  </span>
                  <span>SLA {fmtDuration(p.timeout_seconds)}</span>
                  <span>{TIMEOUT_ACTION_LABEL[p.on_timeout]}</span>
                  <span>{p.auto_approve_below_risk ? 'auto-approve low risk' : 'all risk reviewed'}</span>
                  <span>reviewers: {p.min_reviewers}</span>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...p })}>Edit</button>
                <button
                  className={`switch${p.enabled ? ' on' : ''}`}
                  role="switch"
                  aria-checked={p.enabled}
                  aria-label={`${p.enabled ? 'Disable' : 'Enable'} ${p.name}`}
                  onClick={() => toggle(p)}
                />
              </div>
            </div>
          ))}
          <div className="text-faint small mt" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <ShieldIcon size={12} /> Policies are matched to requests by risk level; the SLA engine applies them in the background.
          </div>
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
      <div className="modal" role="dialog" aria-modal="true" aria-label={isNew ? 'New policy' : 'Edit policy'} onClick={(e) => e.stopPropagation()}>
        <h3>{isNew ? 'New policy' : 'Edit policy'}</h3>
        {!isNew && <div className="modal-sub">{form.name}</div>}
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
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            {['low', 'medium', 'high', 'critical'].map((r) => (
              <label key={r} className="small" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
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
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={!!form.auto_approve_below_risk} onChange={(e) => set('auto_approve_below_risk', e.target.checked)} />
            Auto-approve below-risk actions instantly
          </label>
        </div>
        <div className="field">
          <label>Min reviewers</label>
          <input type="number" min={1} max={10} value={form.min_reviewers ?? 1} onChange={(e) => set('min_reviewers', Number(e.target.value))} />
        </div>
        <div className="modal-actions">
          <button className="btn btn-sm btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-sm btn-primary" onClick={onSave}>Save</button>
        </div>
      </div>
    </div>
  )
}

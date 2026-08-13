import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { fmtDuration, RISK_COLOR } from '../lib/format'
import type { Metrics, RiskLevel } from '../types'
import { useLive } from '../lib/useLive'

const RATES: { key: keyof Metrics['governance']; label: string; hint: string; goodWhen: 'low' | 'high' }[] = [
  { key: 'escalation_rate', label: 'Escalation rate', hint: 'requests escalated vs created', goodWhen: 'low' },
  { key: 'timeout_rate', label: 'Timeout rate', hint: 'auto-decided by SLA vs decided', goodWhen: 'low' },
  { key: 'correction_rate', label: 'Human correction rate', hint: 'reviews where human changed the payload', goodWhen: 'high' },
  { key: 'reviewer_agreement', label: 'Reviewer agreement', hint: 'reviews confirming the agent unchanged', goodWhen: 'high' },
  { key: 'error_escape_rate', label: 'Error escape rate', hint: 'approved actions with negative outcome', goodWhen: 'low' },
  { key: 'sla_compliance_rate', label: 'SLA compliance', hint: 'decisions reached before deadline', goodWhen: 'high' },
]

export function Metrics() {
  const [m, setM] = useState<Metrics | null>(null)
  const [since, setSince] = useState('')
  const live = useLive(['decisions', 'requests'])

  const load = useCallback(async (days?: string) => {
    const d = await api.metrics(days || undefined)
    setM(d)
    setSince(days || '')
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(() => load(since || undefined), 8000)
    return () => clearInterval(t)
  }, [load, since])

  useEffect(() => {
    if (live.revision > 0) load(since || undefined)
  }, [live.revision, load, since])

  if (!m) {
    return (
      <div className="empty">
        <span className="spinner" />
        <div>computing metrics…</div>
      </div>
    )
  }

  const g = m.governance

  const gaugeColor = (rate: number, goodWhen: 'low' | 'high') => {
    const bad = goodWhen === 'low' ? rate > 40 : rate < 60
    const warn = goodWhen === 'low' ? rate > 20 : rate < 80
    if (bad) return 'var(--red)'
    if (warn) return 'var(--amber)'
    return 'var(--green)'
  }

  return (
    <>
      <div className="topbar">
        <div>
          <h1>Governance Metrics</h1>
          <div className="sub">Control-plane KPIs computed from the decision log &amp; feedback loop</div>
        </div>
        <div className="live">
          <span className={`dot${live.live ? ' pulse' : ''}`} />
          <select className="ctl" value={since} onChange={(e) => load(e.target.value)}>
            <option value="">All time</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
          </select>
        </div>
      </div>

      <div className="grid stats" style={{ marginBottom: 18 }}>
        <div className="card">
          <div className="stat-value">{m.totals.requests}</div>
          <div className="stat-label">Total requests</div>
          <div className="stat-sub">{m.totals.pending} pending now</div>
        </div>
        <div className="card">
          <div className="stat-value">{m.totals.escalated}</div>
          <div className="stat-label">Escalated</div>
          <div className="stat-sub">{g.escalation_rate}% of requests</div>
        </div>
        <div className="card">
          <div className="stat-value mono">{fmtDuration(m.latency.avg_seconds)}</div>
          <div className="stat-label">Avg review latency</div>
          <div className="stat-sub">p50 {fmtDuration(m.latency.p50_seconds)} · p95 {fmtDuration(m.latency.p95_seconds)}</div>
        </div>
        <div className="card">
          <div className="stat-value">{m.latency.human_reviews}</div>
          <div className="stat-label">Human reviews</div>
          <div className="stat-sub">{m.feedback.approved_with_feedback} with outcome feedback</div>
        </div>
      </div>

      <div className="grid two-col">
        <div className="card">
          <h3>Governance rates</h3>
          {RATES.map((r) => (
            <div className="gauge-row" key={r.key}>
              <div className="gauge-label" title={r.hint}>{r.label}<div className="text-faint small">{r.hint}</div></div>
              <div className="gauge">
                <div className="gauge-fill" style={{ width: `${Math.min(100, g[r.key])}%`, background: gaugeColor(g[r.key], r.goodWhen) }} />
              </div>
              <div className="gauge-pct">{g[r.key]}%</div>
            </div>
          ))}
        </div>

        <div className="card">
          <h3>Risk breakdown</h3>
          {(Object.entries(m.risk) as [RiskLevel, { created: number; escalated: number }][]).map(([level, v]) => (
            <div className="bar-row" key={level}>
              <div className="label">
                <span className="risk-dot" style={{ background: RISK_COLOR[level] }} />
                {level}
              </div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${v.created ? Math.min(100, (v.escalated / Math.max(1, v.created)) * 100) : 0}%`, background: `linear-gradient(90deg, ${RISK_COLOR[level]}, ${RISK_COLOR[level]}aa)` }} />
              </div>
              <div className="bar-val">{v.escalated}/{v.created}</div>
            </div>
          ))}
          <div className="text-faint small mt">bars show escalated / created per risk level</div>
          <h3 className="mt">Status mix</h3>
          {Object.entries(m.totals.by_status).filter(([, n]) => n > 0).map(([s, n]) => (
            <div className="bar-row" key={s}>
              <div className="label" style={{ textTransform: 'capitalize' }}>{s.replace('_', ' ')}</div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(n / m.totals.requests) * 100}%` }} />
              </div>
              <div className="bar-val">{n}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { fmtClock, timeAgo } from '../lib/format'
import type { DecisionLog } from '../types'
import { DeltaView } from '../components/DeltaView'

const SOURCE_LABEL: Record<string, string> = {
  human_review: 'Human review',
  policy_timeout: 'Policy timeout',
  auto_policy: 'Auto policy',
  agent_feedback: 'Agent feedback',
}

export function Decisions() {
  const [rows, setRows] = useState<DecisionLog[]>([])
  const [total, setTotal] = useState(0)
  const [source, setSource] = useState('')
  const [agreement, setAgreement] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const d = await api.listDecisions({
        source: source || undefined,
        agreement: agreement === '' ? undefined : agreement === 'true',
        limit: 200,
      })
      setRows(d.items)
      setTotal(d.total)
    } finally {
      setLoading(false)
    }
  }, [source, agreement])

  useEffect(() => {
    load()
    const t = setInterval(load, 6000)
    return () => clearInterval(t)
  }, [load])

  return (
    <>
      <div className="topbar">
        <div>
          <h1>Decision Log</h1>
          <div className="sub">Model decision vs human decision deltas — the feedback data that calibrates HITL thresholds</div>
        </div>
        <div className="live"><span className="dot" /> {total} decisions</div>
      </div>

      <div className="filterbar">
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">All sources</option>
          <option value="human_review">Human review</option>
          <option value="policy_timeout">Policy timeout</option>
          <option value="auto_policy">Auto policy</option>
          <option value="agent_feedback">Agent feedback</option>
        </select>
        <select value={agreement} onChange={(e) => setAgreement(e.target.value)}>
          <option value="">Agreement: all</option>
          <option value="true">Agreed (no delta)</option>
          <option value="false">Disagreed (delta)</option>
        </select>
      </div>

      {loading ? (
        <div className="empty"><span className="spinner" /> loading…</div>
      ) : rows.length === 0 ? (
        <div className="empty">No decision records found.</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Request</th>
                <th>Source</th>
                <th>Delta (human vs agent)</th>
                <th>Agreement</th>
                <th>Reviewer / Note</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td className="mono small">{d.request_ref}</td>
                  <td><span className="badge pending">{SOURCE_LABEL[d.source]}</span></td>
                  <td style={{ minWidth: 220 }}><DeltaView log={d} /></td>
                  <td>
                    {d.agreement === null ? (
                      <span className="text-faint">—</span>
                    ) : d.agreement ? (
                      <span style={{ color: 'var(--green)' }}>✓ agreed</span>
                    ) : (
                      <span style={{ color: 'var(--red)' }}>✗ corrected</span>
                    )}
                  </td>
                  <td className="small">
                    <div className="mono text-dim">{d.reviewer_id ?? '—'}</div>
                    {d.note && <div className="text-faint">{d.note}</div>}
                  </td>
                  <td className="small mono text-dim" title={fmtClock(d.created_at)}>{timeAgo(d.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

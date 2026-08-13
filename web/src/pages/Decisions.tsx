import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { fmtClock, timeAgo } from '../lib/format'
import type { DecisionLog } from '../types'
import { DeltaView } from '../components/DeltaView'
import { useLive } from '../lib/useLive'

const SOURCE_LABEL: Record<string, string> = {
  human_review: 'Human review',
  policy_timeout: 'Policy timeout',
  auto_policy: 'Auto policy',
  agent_feedback: 'Agent feedback',
}

const PAGE = 50

export function Decisions() {
  const [rows, setRows] = useState<DecisionLog[]>([])
  const [total, setTotal] = useState(0)
  const [source, setSource] = useState('')
  const [agreement, setAgreement] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [q, setQ] = useState('')
  const offsetRef = useRef(0)
  const live = useLive(['decisions', 'requests'])

  const load = useCallback(async (mode: 'replace' | 'append' = 'replace') => {
    const start = mode === 'replace' ? 0 : offsetRef.current
    const d = await api.listDecisions({
      source: source || undefined,
      agreement: agreement === '' ? undefined : agreement === 'true',
      q: q || undefined,
      limit: PAGE,
      offset: start,
    })
    setRows((prev) => (mode === 'replace' ? d.items : [...prev, ...d.items]))
    setTotal(d.total)
    offsetRef.current = start + d.items.length
  }, [source, agreement, q])

  useEffect(() => {
    setLoading(true)
    load()
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [source, agreement, q, load])

  // refresh from the live event bus on decision / request events
  useEffect(() => {
    if (live.revision > 0) load()
  }, [live.revision, load])

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      await load('append')
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <>
      <div className="topbar">
        <div>
          <h1>Decision Log</h1>
          <div className="sub">Model decision vs human decision deltas — the feedback data that calibrates HITL thresholds</div>
        </div>
        <div className="live">
          <span className={`dot${live.live ? ' pulse' : ''}`} />
          {total} decisions · {live.live ? 'live' : 'polling'}
        </div>
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
        <input type="search" placeholder="Search request ref / reviewer…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {loading ? (
        <div className="card">
          {[0, 1, 2, 3, 4].map((i) => (
            <div className="skeleton" key={i} style={{ height: 18, marginBottom: 16 }} />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="empty">
          <div className="empty-ico">⌾</div>
          <div>No decision records found.</div>
          <div className="empty-hint">Decisions appear here after approvals, rejections, SLA timeouts or agent feedback.</div>
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap">
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
                        <span style={{ color: 'var(--green)', fontWeight: 600 }}>✓ agreed</span>
                      ) : (
                        <span style={{ color: 'var(--red)', fontWeight: 600 }}>✗ corrected</span>
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
          {rows.length < total && (
            <div style={{ padding: '14px 16px', textAlign: 'center' }}>
              <button className="btn btn-sm btn-ghost" onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? 'Loading…' : `Load more (${total - rows.length} remaining)`}
              </button>
            </div>
          )}
        </div>
      )}
    </>
  )
}

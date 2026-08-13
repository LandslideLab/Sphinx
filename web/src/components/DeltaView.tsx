import type { DecisionLog } from '../types'

export function DeltaView({ log }: { log: DecisionLog }) {
  if (!log.delta || log.delta.length === 0) {
    return <span className="delta"><span className="op-add">✓ no delta — human confirmed agent decision</span></span>
  }
  return (
    <div className="delta">
      {log.delta.map((d, i) => (
        <span key={i} className={`op-${d.op}`}>
          {d.op === 'add' && `+ ${d.path} = ${JSON.stringify(d.to)}`}
          {d.op === 'remove' && `− ${d.path} (was ${JSON.stringify(d.from)})`}
          {d.op === 'replace' && `~ ${d.path}: ${JSON.stringify(d.from)} → ${JSON.stringify(d.to)}`}
        </span>
      ))}
    </div>
  )
}

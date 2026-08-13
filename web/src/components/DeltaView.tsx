import type { DecisionLog } from '../types'

export function DeltaView({ log }: { log: DecisionLog }) {
  if (!log.delta || log.delta.length === 0) {
    return (
      <span className="delta">
        <span className="op op-none">✓ no delta — human confirmed agent decision</span>
      </span>
    )
  }
  return (
    <div className="delta">
      {log.delta.map((d, i) => (
        <span key={i} className={`op op-${d.op}`}>
          {d.op === 'add' && <><b>+</b> {d.path} = {JSON.stringify(d.to)}</>}
          {d.op === 'remove' && <><b>−</b> {d.path} (was {JSON.stringify(d.from)})</>}
          {d.op === 'replace' && <><b>~</b> {d.path}: {JSON.stringify(d.from)} → {JSON.stringify(d.to)}</>}
        </span>
      ))}
    </div>
  )
}

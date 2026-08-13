import { useEffect, useState } from 'react'

export function Countdown({ deadlineIso, timeoutSeconds }: { deadlineIso: string; timeoutSeconds: number | null }) {
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const deadline = new Date(deadlineIso).getTime() + (timeoutSeconds ?? 0) * 1000
  const remaining = Math.max(0, deadline - now)
  const cls = remaining < 30_000 ? 'countdown danger' : remaining < 90_000 ? 'countdown warn' : 'countdown'
  return (
    <span className={cls} title={`SLA deadline ${new Date(deadline).toLocaleTimeString()}`}>
      ⏱ {fmt(remaining)}
    </span>
  )
}

export function fmtRemaining(ms: number): string {
  const s = Math.floor(ms / 1000)
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
  if (s >= 60) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${s}s`
}

function fmt(ms: number): string {
  return fmtRemaining(ms)
}

import { useEffect, useState } from 'react'
import { api } from './api'

export function usePendingCount(): number {
  const [count, setCount] = useState(0)

  useEffect(() => {
    const load = () => api.listRequests({ status: 'pending', limit: 1 }).then((d) => setCount(d.total)).catch(() => {})
    load()
    const t = setInterval(load, 8000)
    return () => clearInterval(t)
  }, [])

  return count
}

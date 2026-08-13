import { createContext, useCallback, useContext, useState } from 'react'
import type { ReactNode } from 'react'

interface Toast {
  id: number
  kind: 'info' | 'success' | 'error'
  message: string
}

const ToastCtx = createContext<{ push: (message: string, kind?: Toast['kind']) => void }>({ push: () => {} })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])

  const push = useCallback((message: string, kind: Toast['kind'] = 'info') => {
    const id = Date.now() + Math.random()
    setItems((prev) => [...prev, { id, kind, message }])
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 4200)
  }, [])

  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="toast">
        {items.map((t) => (
          <div key={t.id} className={`toast-item ${t.kind}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  return useContext(ToastCtx)
}

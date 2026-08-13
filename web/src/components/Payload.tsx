import { jsonTokens } from '../lib/jsonTokens'

export function Payload({ value, maxHeight = 260 }: { value: Record<string, unknown>; maxHeight?: number }) {
  const text = JSON.stringify(value, null, 2)
  return (
    <pre className="payload" style={{ maxHeight }}>
      <code>{jsonTokens(text)}</code>
    </pre>
  )
}

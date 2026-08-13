import type { ReactNode } from 'react'

/**
 * Minimal, dependency-free JSON tokenizer for syntax-highlighted payloads.
 * Preserves the exact pretty-printed layout (whitespace kept verbatim) so the
 * parent `<pre>` keeps its formatting.
 */
export function jsonTokens(text: string): ReactNode[] {
  const out: ReactNode[] = []
  let i = 0
  let k = 0
  const len = text.length
  while (i < len) {
    const ch = text[i]
    if (ch === '"') {
      let j = i + 1
      let str = '"'
      while (j < len) {
        const c = text[j]
        str += c
        if (c === '\\') {
          j += 1
          str += text[j] ?? ''
          j += 1
          continue
        }
        if (c === '"') {
          j += 1
          break
        }
        j += 1
      }
      const isKey = /^\s*:/.test(text.slice(j))
      const kid = k
      k += 1
      out.push(
        <span key={kid} className={isKey ? 'key' : 'str'}>
          {str}
        </span>,
      )
      i = j
    } else if (ch === '-' || (ch >= '0' && ch <= '9')) {
      let j = i + 1
      while (j < len && /[0-9.eE+-]/.test(text[j])) j += 1
      const kid = k
      k += 1
      out.push(
        <span key={kid} className="num">
          {text.slice(i, j)}
        </span>,
      )
      i = j
    } else if (text.startsWith('true', i) || text.startsWith('false', i) || text.startsWith('null', i)) {
      const tok = text.startsWith('true', i) ? 'true' : text.startsWith('false', i) ? 'false' : 'null'
      const kid = k
      k += 1
      out.push(
        <span key={kid} className="num">
          {tok}
        </span>,
      )
      i += tok.length
    } else {
      out.push(text[i])
      i += 1
    }
  }
  return out
}

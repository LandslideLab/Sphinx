import { describe, it, expect } from 'vitest'
import type { ReactNode } from 'react'
import { jsonTokens } from './jsonTokens'

function flatText(tokens: ReactNode[]): string {
  return tokens
    .map((t) => {
      if (typeof t === 'string') return t
      const el = t as { props: { children?: ReactNode | string } }
      const c = el.props.children
      return typeof c === 'string' ? c : ''
    })
    .join('')
}

describe('jsonTokens', () => {
  it('highlights keys, strings and numbers', () => {
    const tokens = jsonTokens(JSON.stringify({ name: 'refund', amount: 42.5, ok: true }, null, 2))
    const text = flatText(tokens)
    expect(text).toContain('"name"')
    expect(text).toContain('42.5')
    expect(text).toContain('true')
    expect(tokens.some((t) => typeof t === 'object')).toBe(true)
  })

  it('escaped strings do not break tokenizing', () => {
    const src = JSON.stringify({ note: 'he said "hi"\\nbye' }, null, 2)
    const tokens = jsonTokens(src)
    const text = flatText(tokens)
    expect(text).toContain('he said \\"hi\\"')
  })

  it('round-trips the source text exactly', () => {
    const value = { a: [1, 2, { b: 'x' }], c: null, d: false }
    const src = JSON.stringify(value, null, 2)
    expect(flatText(jsonTokens(src))).toBe(src)
  })
})

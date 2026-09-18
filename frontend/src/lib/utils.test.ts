import { describe, it, expect } from 'vitest'
import { cn } from './utils'

describe('cn', () => {
  it('merges plain class names', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('drops falsy values', () => {
    expect(cn('a', false, null, undefined, '', 'b')).toBe('a b')
  })

  it('lets a later Tailwind class win a conflict (tailwind-merge)', () => {
    // twMerge should keep only the last conflicting utility.
    expect(cn('p-2', 'p-4')).toBe('p-4')
    expect(cn('rounded-lg', 'rounded-none')).toBe('rounded-none')
  })

  it('supports conditional object syntax', () => {
    expect(cn('base', { active: true, hidden: false })).toBe('base active')
  })
})

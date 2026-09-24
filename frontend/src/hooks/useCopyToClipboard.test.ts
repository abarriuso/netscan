import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useCopyToClipboard } from './useNetscan'

describe('useCopyToClipboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('starts with nothing copied', () => {
    const { result } = renderHook(() => useCopyToClipboard())
    expect(result.current.copied).toBeNull()
  })

  it('writes to the async clipboard and flags the copied value', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    const { result } = renderHook(() => useCopyToClipboard())
    let ok = false
    await act(async () => {
      ok = await result.current.copy('192.168.1.10')
    })
    expect(ok).toBe(true)
    expect(writeText).toHaveBeenCalledWith('192.168.1.10')
    expect(result.current.copied).toBe('192.168.1.10')
  })

  it('clears the copied flag after the reset timeout', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    const { result } = renderHook(() => useCopyToClipboard(20))
    await act(async () => {
      await result.current.copy('aa:bb:cc')
    })
    expect(result.current.copied).toBe('aa:bb:cc')
    await waitFor(() => expect(result.current.copied).toBeNull(), { timeout: 200 })
  })

  it('returns false when the clipboard write rejects', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    Object.assign(navigator, { clipboard: { writeText } })

    const { result } = renderHook(() => useCopyToClipboard())
    let ok = true
    await act(async () => {
      ok = await result.current.copy('x')
    })
    expect(ok).toBe(false)
    expect(result.current.copied).toBeNull()
  })

  it('falls back to execCommand when the async clipboard is unavailable', async () => {
    // No navigator.clipboard -> hidden-textarea + execCommand path.
    Object.assign(navigator, { clipboard: undefined })
    const exec = vi.fn().mockReturnValue(true)
    Object.assign(document, { execCommand: exec })

    const { result } = renderHook(() => useCopyToClipboard())
    let ok = false
    await act(async () => {
      ok = await result.current.copy('fallback-value')
    })
    expect(ok).toBe(true)
    expect(exec).toHaveBeenCalledWith('copy')
    expect(result.current.copied).toBe('fallback-value')
  })
})

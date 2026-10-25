import { describe, expect, it } from 'vitest'
import { toLine } from './eventStream'
import { clearFront, frontLines, logFront, subscribeFront } from './telemetry'

describe('frontend telemetry', () => {
  it('records lines with origin, level and data, and notifies once per burst', async () => {
    clearFront()
    let notified = 0
    const off = subscribeFront(() => notified++)
    logFront('http', 'GET /api/devices → 200 · 3.1 ms', 'debug', { status: 200 })
    logFront('ui', 'tab → mapa')
    await Promise.resolve()
    off()
    const lines = frontLines()
    expect(lines).toHaveLength(2)
    expect(lines[0]).toMatchObject({ origin: 'front', source: 'http', level: 'debug', data: { status: 200 } })
    expect(lines[1].level).toBe('info')
    expect(lines[1].t).toBeGreaterThanOrEqual(lines[0].t)
    expect(notified).toBe(1) // coalesced into one microtask
  })
})

describe('backend event mapping', () => {
  it('turns a bus event into a terminal line keyed by seq', () => {
    const line = toLine({ seq: 42, ts: '2026-10-24T07:05:09.042', level: 'warning', source: 'live', msg: 'down' })
    expect(line).toMatchObject({ id: 'be-42', origin: 'back', seq: 42, level: 'warning', source: 'live', msg: 'down' })
    // naive ISO from the server = local wall-clock time
    expect(new Date(line.t).getMilliseconds()).toBe(42)
    expect(new Date(line.t).getHours()).toBe(7)
  })
})

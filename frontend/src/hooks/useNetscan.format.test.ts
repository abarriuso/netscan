import { describe, it, expect } from 'vitest'
import { formatBps, formatBytes, formatUptime } from './useNetscan'

describe('formatBps', () => {
  it('returns 0 bps for missing / sub-1 input', () => {
    expect(formatBps()).toBe('0 bps')
    expect(formatBps(0)).toBe('0 bps')
    expect(formatBps(0.4)).toBe('0 bps')
  })

  it('converts bytes/sec to bits/sec and scales units', () => {
    expect(formatBps(1)).toBe('8.0 bps')
    expect(formatBps(1000)).toBe('8.0 Kbps')
    expect(formatBps(1_000_000)).toBe('8.0 Mbps')
    expect(formatBps(1_000_000_000)).toBe('8.0 Gbps')
  })

  it('drops the decimal once the value reaches double digits', () => {
    // 2000 bytes/s = 16 Kbps -> value >= 10 so 0 decimals
    expect(formatBps(2000)).toBe('16 Kbps')
  })

  it('caps at the largest unit (Gbps) instead of inventing new ones', () => {
    expect(formatBps(1_000_000_000_000)).toContain('Gbps')
  })
})

describe('formatBytes', () => {
  it('returns an em dash for missing / zero input', () => {
    expect(formatBytes()).toBe('—')
    expect(formatBytes(0)).toBe('—')
  })

  it('scales with binary (1024) units', () => {
    expect(formatBytes(512)).toBe('512.0 B')
    expect(formatBytes(1024)).toBe('1.0 KiB')
    expect(formatBytes(1024 * 1024)).toBe('1.0 MiB')
    expect(formatBytes(1024 ** 3)).toBe('1.0 GiB')
    expect(formatBytes(1024 ** 4)).toBe('1.0 TiB')
  })

  it('always keeps one decimal place', () => {
    expect(formatBytes(1536)).toBe('1.5 KiB')
  })
})

describe('formatUptime', () => {
  it('returns an em dash for missing / zero seconds', () => {
    expect(formatUptime()).toBe('—')
    expect(formatUptime(0)).toBe('—')
  })

  it('shows days + hours once past a day', () => {
    const oneDayTwoHours = 86400 + 2 * 3600
    expect(formatUptime(oneDayTwoHours)).toBe('1d 2h')
  })

  it('shows hours + minutes when under a day', () => {
    const threeHours25Min = 3 * 3600 + 25 * 60
    expect(formatUptime(threeHours25Min)).toBe('3h 25m')
  })

  it('handles a bare number of minutes (0 hours)', () => {
    expect(formatUptime(45 * 60)).toBe('0h 45m')
  })
})

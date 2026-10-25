import { describe, expect, it } from 'vitest'
import {
  availabilityTone,
  fmtAvailability,
  fmtBitRate,
  fmtByteRate,
  fmtBytes,
  fmtClockMs,
  fmtDuration,
  fmtMbps,
  fmtMs,
  fmtPct,
  rttTone,
} from './format'

describe('unit formatting', () => {
  it('never renders missing data as zero', () => {
    for (const f of [fmtMs, fmtDuration, fmtBytes, fmtByteRate, fmtBitRate, fmtMbps, fmtPct, fmtAvailability]) {
      expect(f(null)).toBe('—')
      expect(f(undefined)).toBe('—')
      expect(f(Number.NaN)).toBe('—')
    }
  })

  it('milliseconds keep sub-ms precision on a LAN and switch to seconds late', () => {
    expect(fmtMs(0)).toBe('0.00 ms')
    expect(fmtMs(0.412)).toBe('0.41 ms')
    expect(fmtMs(3.66)).toBe('3.7 ms')
    expect(fmtMs(125.4)).toBe('125 ms')
    expect(fmtMs(2350)).toBe('2350 ms')
    expect(fmtMs(12_345)).toBe('12.35 s')
  })

  it('durations show the two most significant units', () => {
    expect(fmtDuration(42)).toBe('42 s')
    expect(fmtDuration(192)).toBe('3 min 12 s')
    expect(fmtDuration(5 * 3600 + 3 * 60)).toBe('5 h 03 min')
    expect(fmtDuration(2 * 86400 + 4 * 3600 + 59)).toBe('2 d 4 h')
  })

  it('sizes use IEC (1024) prefixes', () => {
    expect(fmtBytes(512)).toBe('512 B')
    expect(fmtBytes(1024)).toBe('1.00 KiB')
    expect(fmtBytes(3.5 * 1024 * 1024)).toBe('3.50 MiB')
    expect(fmtBytes(250 * 1024 ** 3)).toBe('250.0 GiB')
  })

  it('rates are bits per second with SI (1000) prefixes', () => {
    expect(fmtBitRate(850)).toBe('850 bit/s')
    expect(fmtBitRate(12_400)).toBe('12.4 kbit/s')
    expect(fmtBitRate(940_000_000)).toBe('940 Mbit/s')
    expect(fmtBitRate(2_500_000_000)).toBe('2.50 Gbit/s')
    // 1 MB/s of payload = 8 Mbit/s on the wire counter
    expect(fmtByteRate(1_000_000)).toBe('8.00 Mbit/s')
    expect(fmtMbps(941.2)).toBe('941 Mbit/s')
  })

  it('availability gains decimals where they matter', () => {
    expect(fmtAvailability(100)).toBe('100 %')
    expect(fmtAvailability(99.996)).toBe('100 %')
    expect(fmtAvailability(99.95)).toBe('99.95 %')
    expect(fmtAvailability(97.25)).toBe('97.3 %')
    expect(fmtPct(33.333, 1)).toBe('33.3 %')
  })

  it('tones follow the documented thresholds', () => {
    expect(availabilityTone(99.5)).toBe('ok')
    expect(availabilityTone(96)).toBe('warn')
    expect(availabilityTone(80)).toBe('bad')
    expect(availabilityTone(null)).toBe('none')
    expect(rttTone(0.4)).toBe('ok')
    expect(rttTone(12)).toBe('warn')
    expect(rttTone(60)).toBe('bad')
  })

  it('log clock keeps milliseconds', () => {
    const t = new Date(2026, 9, 24, 7, 5, 9, 42).getTime()
    expect(fmtClockMs(t)).toBe('07:05:09.042')
  })
})

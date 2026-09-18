import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, hasToken, submitToken, clearToken, invalidateCache } from './api'

// ---- helpers -------------------------------------------------------------
function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('api client', () => {
  beforeEach(() => {
    localStorage.clear()
    invalidateCache()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('token storage', () => {
    it('reports no token by default', () => {
      expect(hasToken()).toBe(false)
    })

    it('persists a submitted token to localStorage', () => {
      submitToken('secret-123')
      expect(hasToken()).toBe(true)
      expect(localStorage.getItem('netscan_token')).toBe('secret-123')
    })

    it('clears a stored token', () => {
      submitToken('secret-123')
      clearToken()
      expect(hasToken()).toBe(false)
    })
  })

  describe('GET requests', () => {
    it('hits the expected path and returns parsed JSON', async () => {
      const fetchMock = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(jsonResponse([{ id: 1 }]))
      const out = await api.devices()
      expect(out).toEqual([{ id: 1 }])
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(fetchMock.mock.calls[0][0]).toBe('/api/devices')
    })

    it('sends the X-API-Key header only when a token is set', async () => {
      const fetchMock = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(jsonResponse({ ok: true }))

      await api.overview()
      const headersNoToken = (fetchMock.mock.calls[0][1]?.headers ?? {}) as Record<string, string>
      expect(headersNoToken['X-API-Key']).toBeUndefined()

      submitToken('abc')
      invalidateCache()
      await api.overview()
      const headersWithToken = (fetchMock.mock.calls[1][1]?.headers ?? {}) as Record<string, string>
      expect(headersWithToken['X-API-Key']).toBe('abc')
    })

    it('dedups concurrent requests to the same path into one fetch', async () => {
      const fetchMock = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(jsonResponse([]))
      // Fire two in parallel before the first resolves.
      const [a, b] = await Promise.all([api.devices(), api.devices()])
      expect(a).toEqual([])
      expect(b).toEqual([])
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    it('serves a second call from the short-TTL cache (no refetch)', async () => {
      const fetchMock = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(jsonResponse({ v: 1 }))
      await api.overview()
      await api.overview() // within CACHE_TTL_MS -> cached
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    it('refetches after the cache is invalidated', async () => {
      const fetchMock = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(jsonResponse({ v: 1 }))
      await api.overview()
      invalidateCache()
      await api.overview()
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })

    it('throws with the path + status on a non-ok response', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}, 500))
      await expect(api.system()).rejects.toThrow('/api/system: 500')
    })

    it('URL-encodes a device MAC into the metrics path', async () => {
      const fetchMock = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(jsonResponse({ mac: 'x', samples: [] }))
      await api.deviceMetrics('aa:bb:cc:dd:ee:ff', 30)
      expect(fetchMock.mock.calls[0][0]).toBe(
        '/api/devices/aa%3Abb%3Acc%3Add%3Aee%3Aff/metrics?limit=30',
      )
    })
  })

  describe('mutations', () => {
    it('POSTs a scan and invalidates cached GETs afterward', async () => {
      const fetchMock = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValueOnce(jsonResponse({ v: 1 })) // overview #1
        .mockResolvedValueOnce(jsonResponse({ status: 'ok' })) // startScan POST
        .mockResolvedValueOnce(jsonResponse({ v: 2 })) // overview #2

      await api.overview()
      await api.startScan({ full: true })
      // Cache was invalidated by the mutation, so this refetches.
      await api.overview()

      expect(fetchMock).toHaveBeenCalledTimes(3)
      const postCall = fetchMock.mock.calls[1]
      expect(postCall[0]).toBe('/api/scans')
      expect(postCall[1]?.method).toBe('POST')
      expect(postCall[1]?.body).toBe(JSON.stringify({ full: true }))
    })

    it('PATCHes device trust with the right body', async () => {
      const fetchMock = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(jsonResponse({ ok: true }))
      await api.setTrusted('aa:bb', false)
      const call = fetchMock.mock.calls[0]
      expect(call[0]).toBe('/api/devices/aa%3Abb')
      expect(call[1]?.method).toBe('PATCH')
      expect(call[1]?.body).toBe(JSON.stringify({ trusted: false }))
    })
  })
})

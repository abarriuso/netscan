import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, hasToken, submitToken, clearToken, invalidateCache, errorFromResponse } from './api'

// ---- helpers -------------------------------------------------------------
function jsonResponse(body: unknown, status = 200): Response {
  const resp = {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: async () => body,
    clone() {
      return jsonResponse(body, status)
    },
  }
  return resp as unknown as Response
}

// A response whose body is not JSON (e.g. a proxy error page) — .json() rejects.
function textResponse(status: number, statusText = ''): Response {
  const resp = {
    ok: false,
    status,
    statusText,
    json: async () => {
      throw new SyntaxError('Unexpected token < in JSON')
    },
    clone() {
      return textResponse(status, statusText)
    },
  }
  return resp as unknown as Response
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

    it('throws the API detail message on a non-ok JSON response', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        jsonResponse({ detail: 'El logo no puede superar 2MB' }, 413),
      )
      await expect(api.system()).rejects.toThrow('El logo no puede superar 2MB')
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

  describe('errorFromResponse', () => {
    it('uses the string detail from the JSON body', async () => {
      const err = await errorFromResponse(jsonResponse({ detail: 'no encontrado' }, 404), '/api/x')
      expect(err.message).toBe('no encontrado')
      expect((err as Error & { status?: number }).status).toBe(404)
      expect((err as Error & { path?: string }).path).toBe('/api/x')
    })

    it('joins FastAPI 422 validation messages', async () => {
      const body = { detail: [{ msg: 'campo requerido' }, { msg: 'debe ser un entero' }] }
      const err = await errorFromResponse(jsonResponse(body, 422), '/api/y')
      expect(err.message).toBe('campo requerido; debe ser un entero')
    })

    it('falls back to a generic message for a 5xx with no JSON body', async () => {
      const err = await errorFromResponse(textResponse(500), '/api/z')
      expect(err.message).toBe('internal server error')
      expect((err as Error & { status?: number }).status).toBe(500)
    })

    it('uses statusText for a 4xx with no usable detail', async () => {
      const err = await errorFromResponse(textResponse(404, 'Not Found'), '/api/z')
      expect(err.message).toBe('Not Found')
    })
  })
})

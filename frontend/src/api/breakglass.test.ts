import { afterEach, describe, expect, it, vi } from 'vitest'

import { breakglassAvailable, breakglassLogin } from './breakglass'

function mockFetch(resp: { ok: boolean; status: number } | Error) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      if (resp instanceof Error) throw resp
      return { ok: resp.ok, status: resp.status, json: async () => ({}) } as unknown as Response
    }),
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('breakglassAvailable', () => {
  it('is true on a 200 probe', async () => {
    mockFetch({ ok: true, status: 200 })
    expect(await breakglassAvailable()).toBe(true)
  })

  it('is false on a 404 (off the listener)', async () => {
    mockFetch({ ok: false, status: 404 })
    expect(await breakglassAvailable()).toBe(false)
  })

  it('is false when the probe throws', async () => {
    mockFetch(new Error('network down'))
    expect(await breakglassAvailable()).toBe(false)
  })
})

describe('breakglassLogin', () => {
  it.each([
    [200, { ok: true }],
    [401, { ok: false, reason: 'invalid' }],
    [403, { ok: false, reason: 'unavailable' }],
    [429, { ok: false, reason: 'throttled' }],
    [503, { ok: false, reason: 'error' }],
  ])('maps status %i to the right result', async (status, expected) => {
    mockFetch({ ok: status < 400, status })
    expect(await breakglassLogin('u', 'p', '123456')).toEqual(expected)
  })

  it('returns a generic error when the request throws', async () => {
    mockFetch(new Error('network down'))
    expect(await breakglassLogin('u', 'p', '123456')).toEqual({ ok: false, reason: 'error' })
  })
})

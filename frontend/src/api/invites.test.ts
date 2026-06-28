import { afterEach, describe, expect, it, vi } from 'vitest'

import { acceptInvite, createInvite, listInvites, previewInvite, revokeInvite } from './invites'

function mockFetch(resp: { ok: boolean; status: number; body?: unknown }) {
  const fetchMock = vi.fn(
    async () =>
      ({
        ok: resp.ok,
        status: resp.status,
        json: async () => resp.body ?? {},
      }) as unknown as Response,
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('invites api', () => {
  it('lists invites', async () => {
    mockFetch({ ok: true, status: 200, body: [{ id: 1, status: 'active' }] })
    expect(await listInvites()).toHaveLength(1)
  })

  it('throws when listing fails', async () => {
    mockFetch({ ok: false, status: 403 })
    await expect(listInvites()).rejects.toThrow(/invites 403/)
  })

  it('creates an invite and returns the one-time token', async () => {
    const fetchMock = mockFetch({
      ok: true,
      status: 201,
      body: { id: 7, token: 'raw-token', expires_at: '2030-01-01T00:00:00Z' },
    })
    const created = await createInvite({ ttl_hours: 24, requestable: ['plex'] })
    expect(created.token).toBe('raw-token')
    expect(fetchMock).toHaveBeenCalledWith('/invites', expect.objectContaining({ method: 'POST' }))
  })

  it('throws when create fails', async () => {
    mockFetch({ ok: false, status: 403 })
    await expect(createInvite({ ttl_hours: 24, requestable: [] })).rejects.toThrow(/create 403/)
  })

  it('revokes an invite', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, body: { id: 7, status: 'revoked' } })
    await revokeInvite(7)
    expect(fetchMock).toHaveBeenCalledWith(
      '/invites/7/revoke',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('throws when revoke fails', async () => {
    mockFetch({ ok: false, status: 409 })
    await expect(revokeInvite(7)).rejects.toThrow(/revoke 409/)
  })

  it('previews a valid invite', async () => {
    mockFetch({ ok: true, status: 200, body: { requestable: ['plex'], grant_providers: [] } })
    const preview = await previewInvite('tok')
    expect(preview?.requestable).toEqual(['plex'])
  })

  it('returns null for an invalid invite preview (404)', async () => {
    mockFetch({ ok: false, status: 404 })
    expect(await previewInvite('tok')).toBeNull()
  })

  it('throws on an unexpected preview error (non-404)', async () => {
    mockFetch({ ok: false, status: 500 })
    await expect(previewInvite('tok')).rejects.toThrow(/preview 500/)
  })

  it('accepts an invite and returns the enroll url', async () => {
    mockFetch({ ok: true, status: 200, body: { enroll_url: 'http://ak/enroll' } })
    expect(await acceptInvite('tok')).toEqual({ ok: true, enroll_url: 'http://ak/enroll' })
  })

  it.each([
    [404, 'gone'],
    [429, 'throttled'],
    [503, 'unavailable'],
    [500, 'error'],
  ])('maps accept status %i to reason %s', async (status, reason) => {
    mockFetch({ ok: false, status })
    expect(await acceptInvite('tok')).toEqual({ ok: false, reason })
  })

  it('returns a generic error when accept throws (network)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network down')
      }),
    )
    expect(await acceptInvite('tok')).toEqual({ ok: false, reason: 'error' })
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'

import { createInvite, listInvites, revokeInvite } from './invites'

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
})

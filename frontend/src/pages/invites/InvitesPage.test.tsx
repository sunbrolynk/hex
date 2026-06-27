import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser } from '../../api/auth'
import { AuthContext } from '../../components/auth/context'
import { InvitesPage } from './InvitesPage'

function json(body: unknown, status = 200): Response {
  return { ok: status < 400, status, json: async () => body } as unknown as Response
}

const ACTIVE = {
  id: 1,
  status: 'active',
  requestable: [],
  grant_providers: [],
  created_at: '2030-01-01T00:00:00Z',
  expires_at: '2030-01-01T00:00:00Z',
  accepted_at: null,
  revoked_at: null,
}

function renderAs(isOwner: boolean) {
  const user: CurrentUser = { id: 1, username: 'owner', email: null, is_owner: isOwner }
  return render(
    <AuthContext.Provider value={{ user, logout: vi.fn() }}>
      <InvitesPage />
    </AuthContext.Provider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('InvitesPage', () => {
  it('shows owner-only for a non-owner', () => {
    vi.stubGlobal('fetch', vi.fn())
    renderAs(false)
    expect(screen.getByText('Owner only.')).toBeInTheDocument()
  })

  it('lists invites for the owner', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json([ACTIVE])),
    )
    renderAs(true)
    expect(await screen.findByText(/#1 — active/)).toBeInTheDocument()
  })

  it('creates an invite and surfaces the one-time link', async () => {
    const fetchMock = vi.fn(async (_url: string | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET').toUpperCase() === 'POST') {
        return json({ id: 2, token: 'raw-tok', expires_at: '2030-01-01T00:00:00Z' })
      }
      return json([])
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAs(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Create invite' }))
    expect(await screen.findByText(/\/invite\/raw-tok/)).toBeInTheDocument()
  })

  it('revokes an active invite', async () => {
    const fetchMock = vi.fn(async (url: string | URL) => {
      if (String(url).includes('/revoke')) return json({ ...ACTIVE, status: 'revoked' })
      return json([ACTIVE])
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAs(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Revoke' }))
    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/invites/1/revoke',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
  })

  it('surfaces an error when the list fails to load', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({}, 403)),
    )
    renderAs(true)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t load invites/i)
  })

  it('surfaces an error when create fails', async () => {
    const fetchMock = vi.fn(async (_url: string | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET').toUpperCase() === 'POST') return json({}, 503)
      return json([])
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAs(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Create invite' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t create/i)
  })

  it('surfaces an error when revoke fails', async () => {
    const fetchMock = vi.fn(async (url: string | URL) => {
      if (String(url).includes('/revoke')) return json({}, 409)
      return json([ACTIVE])
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAs(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Revoke' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t revoke/i)
  })
})

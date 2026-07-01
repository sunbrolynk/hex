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

const MEDIA = {
  id: 'demo-media',
  name: 'Demo Media',
  category: 'media',
  integration_mode: 'sso_group',
  tiers: [
    { key: 'standard', label: 'Standard', description: null },
    { key: 'premium', label: 'Premium', description: null },
  ],
}

interface Opts {
  invites?: unknown
  providers?: unknown
  createStatus?: number
  listStatus?: number
  onPost?: (body: Record<string, unknown>) => void
}

function mockApi(o: Opts = {}) {
  const fetchMock = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const u = String(url)
    const method = (init?.method ?? 'GET').toUpperCase()
    if (u.includes('/providers')) return json(o.providers ?? [])
    if (u.endsWith('/revoke')) return json({ ...ACTIVE, status: 'revoked' })
    if (u.includes('/invites') && method === 'POST') {
      if (init?.body) o.onPost?.(JSON.parse(init.body as string))
      return json(
        { id: 2, token: 'raw-tok', expires_at: '2030-01-01T00:00:00Z' },
        o.createStatus ?? 200,
      )
    }
    if (u.includes('/invites')) return json(o.invites ?? [], o.listStatus ?? 200)
    return json({})
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
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
    mockApi()
    renderAs(false)
    expect(screen.getByText('Owner only.')).toBeInTheDocument()
  })

  it('lists invites for the owner', async () => {
    mockApi({ invites: [ACTIVE] })
    renderAs(true)
    expect(await screen.findByText(/#1 — active/)).toBeInTheDocument()
  })

  it('renders the grantable services from the catalog', async () => {
    mockApi({ providers: [MEDIA] })
    renderAs(true)
    expect(await screen.findByText(/Grant Demo Media/)).toBeInTheDocument()
  })

  it('shows an empty state when no services are available', async () => {
    mockApi({ providers: [] })
    renderAs(true)
    expect(await screen.findByText(/No services available to grant yet/)).toBeInTheDocument()
  })

  it('creates an invite granting a picked service+tier and surfaces the link', async () => {
    let posted: Record<string, unknown> | null = null
    mockApi({ providers: [MEDIA], onPost: (b) => (posted = b) })
    renderAs(true)
    // Grant Demo Media (defaults to the first tier: standard), then pick premium.
    fireEvent.click(await screen.findByRole('checkbox', { name: /Grant Demo Media/ }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'premium' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    expect(await screen.findByText(/\/invite\/raw-tok/)).toBeInTheDocument()
    expect(posted).toEqual(
      expect.objectContaining({ default_grants: { 'demo-media': 'premium' }, requestable: [] }),
    )
  })

  it('sends a requestable-only selection without a grant', async () => {
    let posted: Record<string, unknown> | null = null
    mockApi({ providers: [MEDIA], onPost: (b) => (posted = b) })
    renderAs(true)
    fireEvent.click(await screen.findByRole('checkbox', { name: /Requestable later/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    await screen.findByText(/\/invite\/raw-tok/)
    expect(posted).toEqual(
      expect.objectContaining({ default_grants: {}, requestable: ['demo-media'] }),
    )
  })

  it('surfaces an error when the list fails to load', async () => {
    mockApi({ listStatus: 403 })
    renderAs(true)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t load invites/i)
  })

  it('surfaces an error when create fails', async () => {
    mockApi({ createStatus: 503 })
    renderAs(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Create invite' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t create/i)
  })

  it('revokes an active invite', async () => {
    const fetchMock = mockApi({ invites: [ACTIVE] })
    renderAs(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Revoke' }))
    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/invites/1/revoke',
        expect.objectContaining({ method: 'POST' }),
      ),
    )
  })
})

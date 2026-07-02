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
  recipient: null,
  recipient_kind: null,
  created_at: '2030-01-01T00:00:00Z',
  expires_at: '2030-01-01T00:00:00Z',
  accepted_at: null,
  revoked_at: null,
}

// A provider that offers a real choice (2 tiers → a Level picker should appear when granted).
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
// A single-option provider (no meaningful level → no Level picker).
const SINGLE = {
  id: 'demo-x',
  name: 'Demo X',
  category: 'misc',
  integration_mode: 'sso_group',
  tiers: [{ key: 'default', label: 'Default', description: null }],
}

interface Opts {
  invites?: Record<string, unknown>[]
  total?: number
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
    if (u.includes('/invites')) {
      const items = o.invites ?? []
      return json(
        { items, total: o.total ?? items.length, limit: 25, offset: 0 },
        o.listStatus ?? 200,
      )
    }
    return json({})
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

// The last GET /invites query string the mock saw — asserts pagination params.
function lastListUrl(fetchMock: ReturnType<typeof mockApi>): string {
  const calls = fetchMock.mock.calls.map((c) => String(c[0]))
  return calls.filter((u) => u.includes('/invites') && !u.endsWith('/revoke')).at(-1) ?? ''
}

function renderAs(isOwner: boolean) {
  const user: CurrentUser = { id: 1, username: 'owner', email: null, is_owner: isOwner }
  return render(
    <AuthContext.Provider value={{ user, logout: vi.fn() }}>
      <InvitesPage />
    </AuthContext.Provider>,
  )
}

const addPicker = () => screen.findByRole('combobox', { name: 'Add a service' })

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

  it('offers the catalog services in the add-a-service dropdown', async () => {
    mockApi({ providers: [MEDIA] })
    renderAs(true)
    expect(await screen.findByRole('option', { name: /Demo Media/ })).toBeInTheDocument()
  })

  it('shows an empty state when no services exist', async () => {
    mockApi({ providers: [] })
    renderAs(true)
    expect(await screen.findByText(/No services available yet/)).toBeInTheDocument()
  })

  it('grants an added service at a chosen level and sends the tier key', async () => {
    let posted: Record<string, unknown> | null = null
    mockApi({ providers: [MEDIA], onPost: (b) => (posted = b) })
    renderAs(true)
    fireEvent.change(await screen.findByRole('combobox', { name: 'Add a service' }), {
      target: { value: 'demo-media' },
    })
    // 2-tier provider → a Level picker appears; choose Premium.
    fireEvent.change(screen.getByRole('combobox', { name: 'Level' }), {
      target: { value: 'premium' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    expect(await screen.findByText(/\/invite\/raw-tok/)).toBeInTheDocument()
    expect(posted).toEqual(
      expect.objectContaining({ default_grants: { 'demo-media': 'premium' }, requestable: [] }),
    )
  })

  it('shows no level picker for a single-option service and sends its only tier', async () => {
    let posted: Record<string, unknown> | null = null
    mockApi({ providers: [SINGLE], onPost: (b) => (posted = b) })
    renderAs(true)
    fireEvent.change(await addPicker(), { target: { value: 'demo-x' } })
    expect(screen.queryByRole('combobox', { name: 'Level' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    await screen.findByText(/\/invite\/raw-tok/)
    expect(posted).toEqual(
      expect.objectContaining({ default_grants: { 'demo-x': 'default' }, requestable: [] }),
    )
  })

  it('marks an added service requestable-only', async () => {
    let posted: Record<string, unknown> | null = null
    mockApi({ providers: [MEDIA], onPost: (b) => (posted = b) })
    renderAs(true)
    fireEvent.change(await addPicker(), { target: { value: 'demo-media' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Requestable later' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    await screen.findByText(/\/invite\/raw-tok/)
    expect(posted).toEqual(
      expect.objectContaining({ default_grants: {}, requestable: ['demo-media'] }),
    )
  })

  it('removing an added service returns it to hidden (not sent)', async () => {
    let posted: Record<string, unknown> | null = null
    mockApi({ providers: [MEDIA], onPost: (b) => (posted = b) })
    renderAs(true)
    fireEvent.change(await addPicker(), { target: { value: 'demo-media' } })
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    await screen.findByText(/\/invite\/raw-tok/)
    expect(posted).toEqual(expect.objectContaining({ default_grants: {}, requestable: [] }))
  })

  it('sends a chosen recipient with its kind', async () => {
    let posted: Record<string, unknown> | null = null
    mockApi({ onPost: (b) => (posted = b) })
    renderAs(true)
    fireEvent.change(await screen.findByRole('combobox', { name: 'Recipient type' }), {
      target: { value: 'email' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Recipient' }), {
      target: { value: 'User@Example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create invite' }))
    await screen.findByText(/\/invite\/raw-tok/)
    expect(posted).toEqual(
      expect.objectContaining({ recipient: 'User@Example.com', recipient_kind: 'email' }),
    )
  })

  it('clears the recipient value when the kind changes', async () => {
    mockApi()
    renderAs(true)
    const kind = await screen.findByRole('combobox', { name: 'Recipient type' })
    fireEvent.change(kind, { target: { value: 'email' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Recipient' }), {
      target: { value: 'a@b.com' },
    })
    fireEvent.change(kind, { target: { value: 'phone' } })
    expect(screen.getByRole('textbox', { name: 'Recipient' })).toHaveValue('')
  })

  it('blocks “add another” when a required recipient is empty', async () => {
    let posted: Record<string, unknown> | null = null
    const fetchMock = mockApi({ onPost: (b) => (posted = b) })
    renderAs(true)
    fireEvent.change(await screen.findByRole('combobox', { name: 'Recipient type' }), {
      target: { value: 'email' },
    })
    // leave the required recipient empty
    fireEvent.click(screen.getByRole('button', { name: 'Create & add another' }))
    const posts = fetchMock.mock.calls.filter(
      (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
    )
    expect(posts).toHaveLength(0)
    expect(posted).toBeNull()
  })

  it('omits recipient when no type is chosen', async () => {
    let posted: Record<string, unknown> | null = null
    mockApi({ onPost: (b) => (posted = b) })
    renderAs(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Create invite' }))
    await screen.findByText(/\/invite\/raw-tok/)
    expect(posted).not.toHaveProperty('recipient')
    expect(posted).not.toHaveProperty('recipient_kind')
  })

  it('shows recipient (who) and granted services (what) in the history', async () => {
    mockApi({
      invites: [
        {
          ...ACTIVE,
          recipient: 'a@b.com',
          recipient_kind: 'email',
          grant_providers: ['demo-media'],
        },
      ],
    })
    renderAs(true)
    expect(await screen.findByText(/email: a@b\.com/)).toBeInTheDocument()
    expect(screen.getByText(/grants: demo-media/)).toBeInTheDocument()
  })

  it('pages forward and requests the next offset', async () => {
    const fetchMock = mockApi({ invites: [ACTIVE], total: 60 })
    renderAs(true)
    const next = await screen.findByRole('button', { name: 'Next' })
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    fireEvent.click(next)
    await vi.waitFor(() => expect(lastListUrl(fetchMock)).toMatch(/offset=25/))
  })

  it('changes page size and refetches from the start', async () => {
    const fetchMock = mockApi({ invites: [ACTIVE], total: 60 })
    renderAs(true)
    fireEvent.change(await screen.findByRole('combobox', { name: 'Per page' }), {
      target: { value: '10' },
    })
    await vi.waitFor(() => expect(lastListUrl(fetchMock)).toMatch(/limit=10&offset=0/))
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

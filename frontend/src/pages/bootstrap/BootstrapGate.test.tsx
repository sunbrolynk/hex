import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { BootstrapGate } from './BootstrapGate'

type Resp = { ok: boolean; status: number; body?: unknown }

// Routes fetch by URL substring, so the bootstrap flow's /auth/me probe and the action call
// (unlock / wire / complete) can return different responses in one test.
function mockRoutes(routes: Record<string, Resp>) {
  const fetchMock = vi.fn(async (url: string | URL) => {
    const u = String(url)
    const key = Object.keys(routes).find((k) => u.includes(k))
    const r: Resp = key ? routes[key] : { ok: false, status: 404 }
    return { ok: r.ok, status: r.status, json: async () => r.body ?? {} } as unknown as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const ANON: Record<string, Resp> = { '/auth/me': { ok: false, status: 401 } }
const SIGNED_IN: Record<string, Resp> = {
  '/auth/me': {
    ok: true,
    status: 200,
    body: { id: 1, username: 'owner', email: null, is_owner: false },
  },
}

function enterToken(value: string) {
  fireEvent.change(screen.getByLabelText('Setup token'), { target: { value } })
}

afterEach(() => vi.unstubAllGlobals())

describe('BootstrapGate — token gate (first run)', () => {
  it('disables submit until a token is entered', () => {
    mockRoutes({})
    render(<BootstrapGate phase="first_run" onAdvance={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Begin setup' })).toBeDisabled()
  })

  it('advances on a valid token', async () => {
    const fetchMock = mockRoutes({
      '/setup/unlock': {
        ok: true,
        status: 200,
        body: { phase: 'bootstrap', setup_required: true },
      },
    })
    const onAdvance = vi.fn()
    render(<BootstrapGate phase="first_run" onAdvance={onAdvance} />)

    enterToken('correct-horse-battery-staple')
    fireEvent.click(screen.getByRole('button', { name: 'Begin setup' }))

    expect(fetchMock).toHaveBeenCalledWith(
      '/setup/unlock',
      expect.objectContaining({ method: 'POST' }),
    )
    await vi.waitFor(() => expect(onAdvance).toHaveBeenCalledOnce())
  })

  it.each([
    [401, /not accepted/i],
    [429, /too many attempts/i],
    [423, /locked.*restart hex/i],
    [500, /something went wrong/i],
  ])('shows a message on %i and does not advance', async (status, pattern) => {
    const onAdvance = vi.fn()
    mockRoutes({ '/setup/unlock': { ok: false, status } })
    render(<BootstrapGate phase="first_run" onAdvance={onAdvance} />)

    enterToken('whatever')
    fireEvent.click(screen.getByRole('button', { name: 'Begin setup' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(pattern)
    expect(onAdvance).not.toHaveBeenCalled()
  })
})

describe('BootstrapGate — wiring step (bootstrap, signed out)', () => {
  it('shows the connect-Authentik step', async () => {
    mockRoutes(ANON)
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)
    expect(await screen.findByRole('button', { name: 'Connect Authentik' })).toBeEnabled()
  })

  it('wires Authentik and offers sign-in on success', async () => {
    const fetchMock = mockRoutes({
      ...ANON,
      '/setup/wire': {
        ok: true,
        status: 200,
        body: { ok: true, client_id: 'cid', provider_pk: 7 },
      },
    })
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Connect Authentik' }))

    expect(fetchMock).toHaveBeenCalledWith(
      '/setup/wire',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(
      await screen.findByRole('heading', { name: 'HEx is connected to Authentik' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/auth/login')
  })

  it.each([
    [503, /isn.t reachable yet/i],
    [502, /couldn.t finish configuring/i],
    [500, /something went wrong/i],
  ])('shows a message when wiring returns %i', async (status, pattern) => {
    mockRoutes({ ...ANON, '/setup/wire': { ok: false, status } })
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Connect Authentik' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(pattern)
  })
})

describe('BootstrapGate — owner claim (bootstrap, signed in)', () => {
  it('shows the claim step for a signed-in user', async () => {
    mockRoutes(SIGNED_IN)
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)
    expect(
      await screen.findByRole('heading', { name: 'Claim ownership of HEx' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Claim ownership & finish' })).toBeEnabled()
  })

  it('claims ownership and advances on success', async () => {
    const fetchMock = mockRoutes({ ...SIGNED_IN, '/setup/complete': { ok: true, status: 200 } })
    const onAdvance = vi.fn()
    render(<BootstrapGate phase="bootstrap" onAdvance={onAdvance} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Claim ownership & finish' }))

    expect(fetchMock).toHaveBeenCalledWith(
      '/setup/complete',
      expect.objectContaining({ method: 'POST' }),
    )
    await vi.waitFor(() => expect(onAdvance).toHaveBeenCalledOnce())
  })

  it('shows an error and does not advance when the claim fails', async () => {
    mockRoutes({ ...SIGNED_IN, '/setup/complete': { ok: false, status: 409 } })
    const onAdvance = vi.fn()
    render(<BootstrapGate phase="bootstrap" onAdvance={onAdvance} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Claim ownership & finish' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t finish setup/i)
    expect(onAdvance).not.toHaveBeenCalled()
  })

  it('falls back to the email when no username is set', async () => {
    mockRoutes({
      '/auth/me': {
        ok: true,
        status: 200,
        body: { id: 1, username: null, email: 'owner@example.com', is_owner: false },
      },
    })
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)
    expect(await screen.findByText('owner@example.com')).toBeInTheDocument()
  })

  it('falls back to a generic label when neither username nor email is set', async () => {
    mockRoutes({
      '/auth/me': {
        ok: true,
        status: 200,
        body: { id: 1, username: null, email: null, is_owner: false },
      },
    })
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)
    expect(await screen.findByText('your account')).toBeInTheDocument()
  })

  it('disables the claim button while the request is in flight', async () => {
    let release!: (r: Response) => void
    const pending = new Promise<Response>((r) => {
      release = r
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL) => {
        if (String(url).includes('/auth/me')) {
          return {
            ok: true,
            status: 200,
            json: async () => SIGNED_IN['/auth/me'].body,
          } as unknown as Response
        }
        return pending // /setup/complete stays in flight
      }),
    )
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Claim ownership & finish' }))
    expect(await screen.findByRole('button', { name: 'Finishing…' })).toBeDisabled()
    release({ ok: true, status: 200, json: async () => ({}) } as unknown as Response)
  })
})

describe('BootstrapGate — auth probe failures (bootstrap)', () => {
  it('surfaces an error, not the wire step, when /auth/me 500s', async () => {
    mockRoutes({ '/auth/me': { ok: false, status: 500 } })
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t reach hex/i)
    expect(screen.queryByRole('button', { name: 'Connect Authentik' })).not.toBeInTheDocument()
  })

  it('surfaces an error when the /auth/me probe rejects (network)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network down')
      }),
    )
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t reach hex/i)
  })
})

import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

interface SetupBody {
  phase: string
  setup_required: boolean
}
type MeBody = { id: number; username: string | null; email: string | null; is_owner: boolean }

function mockApi(opts: { setup: SetupBody; me?: MeBody }) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown) => {
      const url = String(input)
      if (url.includes('/setup/status')) {
        return { ok: true, status: 200, json: async () => opts.setup } as unknown as Response
      }
      if (url.includes('/auth/me')) {
        if (!opts.me) {
          return { ok: false, status: 401, json: async () => ({}) } as unknown as Response
        }
        return { ok: true, status: 200, json: async () => opts.me } as unknown as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as unknown as Response
    }),
  )
}

const OWNER: MeBody = { id: 1, username: 'owner', email: 'owner@example.com', is_owner: true }

afterEach(() => {
  vi.unstubAllGlobals()
  window.history.pushState({}, '', '/') // reset location for the gated-route tests
})

describe('App shell', () => {
  it('renders the home landing once setup is complete and the user is signed in', async () => {
    mockApi({ setup: { phase: 'complete', setup_required: false }, me: OWNER })
    render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: 'HEx' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'About' })).toHaveAttribute('href', '/about')
    expect(screen.getByRole('button', { name: 'Log out' })).toBeInTheDocument()
  })
})

describe('break-glass route', () => {
  it('renders break-glass login outside the setup/auth gates', async () => {
    // Even with first-run setup required and no session, /breakglass must render — it exists for
    // exactly when Authentik (and the normal login) is down (ADR 0008).
    mockApi({ setup: { phase: 'first_run', setup_required: true } }) // me → 401
    window.history.pushState({}, '', '/breakglass')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Break-glass sign-in' })).toBeInTheDocument()
    // The gated surfaces are absent — the bypass is scoped to this one route.
    expect(screen.queryByRole('heading', { name: 'Finish setting up HEx' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'About' })).not.toBeInTheDocument()
  })
})

describe('App gating', () => {
  it('shows the bootstrap gate while first-run setup is required', async () => {
    mockApi({ setup: { phase: 'first_run', setup_required: true } })
    render(<App />)
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Finish setting up HEx' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'About' })).not.toBeInTheDocument()
  })

  it('shows the login gate when setup is complete but no session exists', async () => {
    mockApi({ setup: { phase: 'complete', setup_required: false } }) // me → 401
    render(<App />)
    expect(await screen.findByRole('button', { name: 'Log in with Authentik' })).toBeInTheDocument()
    // The app surface stays behind the auth gate.
    expect(screen.queryByRole('link', { name: 'About' })).not.toBeInTheDocument()
  })

  it('surfaces a non-blocking error when HEx is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network down')
      }),
    )
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t reach hex/i)
  })
})

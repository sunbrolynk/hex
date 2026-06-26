import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BreakGlassLogin } from './BreakGlassLogin'

type Resp = { ok: boolean; status: number; body?: unknown }

// Routes by method: GET = availability probe, POST = the login attempt (same URL).
function mockFetch(opts: { available: Resp; login?: Resp }) {
  const fetchMock = vi.fn(async (_url: string | URL, init?: RequestInit) => {
    const r = (init?.method ?? 'GET').toUpperCase() === 'POST' ? opts.login! : opts.available
    return { ok: r.ok, status: r.status, json: async () => r.body ?? {} } as unknown as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const AVAILABLE: Resp = { ok: true, status: 200, body: { available: true } }

function fillForm() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'owner-recovery' } })
  fireEvent.change(screen.getByLabelText('Passphrase'), { target: { value: 'passphrase' } })
  fireEvent.change(screen.getByLabelText('Authenticator code'), { target: { value: '123456' } })
}

const realLocation = window.location

beforeEach(() => {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...realLocation, assign: vi.fn() },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  Object.defineProperty(window, 'location', { configurable: true, value: realLocation })
})

describe('BreakGlassLogin', () => {
  it('renders as not-found off the listener (availability 404)', async () => {
    mockFetch({ available: { ok: false, status: 404 } })
    render(<BreakGlassLogin />)
    expect(await screen.findByText('Not found.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Break-glass sign-in' })).not.toBeInTheDocument()
  })

  it('shows the form when available on the listener', async () => {
    mockFetch({ available: AVAILABLE })
    render(<BreakGlassLogin />)
    expect(await screen.findByRole('heading', { name: 'Break-glass sign-in' })).toBeInTheDocument()
  })

  it('disables submit until every field is filled', async () => {
    mockFetch({ available: AVAILABLE })
    render(<BreakGlassLogin />)
    const button = await screen.findByRole('button', { name: 'Break the glass' })
    expect(button).toBeDisabled()
    fillForm()
    expect(button).toBeEnabled()
  })

  it('navigates home on a successful break-glass sign-in', async () => {
    mockFetch({ available: AVAILABLE, login: { ok: true, status: 200 } })
    render(<BreakGlassLogin />)
    const button = await screen.findByRole('button', { name: 'Break the glass' })
    fillForm()
    fireEvent.click(button)
    await vi.waitFor(() => expect(window.location.assign).toHaveBeenCalledWith('/'))
  })

  it('shows progress and disables the button while signing in', async () => {
    let release!: (r: Response) => void
    const pending = new Promise<Response>((r) => {
      release = r
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string | URL, init?: RequestInit) => {
        if ((init?.method ?? 'GET').toUpperCase() === 'POST') return pending
        return {
          ok: true,
          status: 200,
          json: async () => ({ available: true }),
        } as unknown as Response
      }),
    )
    render(<BreakGlassLogin />)
    const button = await screen.findByRole('button', { name: 'Break the glass' })
    fillForm()
    fireEvent.click(button)
    expect(await screen.findByRole('button', { name: 'Signing in…' })).toBeDisabled()
    release({ ok: true, status: 200, json: async () => ({}) } as unknown as Response)
  })

  it.each([
    [401, /weren’t accepted/i],
    [403, /unavailable while authentik is reachable/i],
    [429, /too many attempts/i],
    [500, /something went wrong/i],
  ])('shows a distinct message on %i and does not navigate', async (status, pattern) => {
    mockFetch({ available: AVAILABLE, login: { ok: false, status } })
    render(<BreakGlassLogin />)
    const button = await screen.findByRole('button', { name: 'Break the glass' })
    fillForm()
    fireEvent.click(button)
    expect(await screen.findByRole('alert')).toHaveTextContent(pattern)
    expect(window.location.assign).not.toHaveBeenCalled()
  })
})

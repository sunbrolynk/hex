import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { BootstrapGate } from './BootstrapGate'

function mockUnlock(response: { ok: boolean; status: number; body?: unknown }) {
  const fetchMock = vi.fn(
    async () =>
      ({
        ok: response.ok,
        status: response.status,
        json: async () => response.body ?? {},
      }) as unknown as Response,
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function enterToken(value: string) {
  fireEvent.change(screen.getByLabelText('Setup token'), { target: { value } })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('BootstrapGate', () => {
  it('disables submit until a token is entered', () => {
    render(<BootstrapGate phase="first_run" onAdvance={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Begin setup' })).toBeDisabled()
  })

  it('advances on a valid token', async () => {
    const fetchMock = mockUnlock({
      ok: true,
      status: 200,
      body: { phase: 'bootstrap', setup_required: true },
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
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows a generic message on a rejected token and does not advance', async () => {
    mockUnlock({ ok: false, status: 401 })
    const onAdvance = vi.fn()
    render(<BootstrapGate phase="first_run" onAdvance={onAdvance} />)

    enterToken('wrong')
    fireEvent.click(screen.getByRole('button', { name: 'Begin setup' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/not accepted/i)
    expect(onAdvance).not.toHaveBeenCalled()
  })

  it('reports throttling distinctly from a bad token', async () => {
    mockUnlock({ ok: false, status: 429 })
    render(<BootstrapGate phase="first_run" onAdvance={vi.fn()} />)

    enterToken('whatever')
    fireEvent.click(screen.getByRole('button', { name: 'Begin setup' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/too many attempts/i)
  })

  it('tells the operator to restart when setup is locked out (423)', async () => {
    mockUnlock({ ok: false, status: 423 })
    const onAdvance = vi.fn()
    render(<BootstrapGate phase="first_run" onAdvance={onAdvance} />)

    enterToken('whatever')
    fireEvent.click(screen.getByRole('button', { name: 'Begin setup' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/locked.*restart hex/i)
    expect(onAdvance).not.toHaveBeenCalled()
  })

  it('shows a generic message on an unexpected server error', async () => {
    mockUnlock({ ok: false, status: 500 })
    render(<BootstrapGate phase="first_run" onAdvance={vi.fn()} />)

    enterToken('whatever')
    fireEvent.click(screen.getByRole('button', { name: 'Begin setup' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/something went wrong/i)
  })

  it('shows the connect-Authentik step once past first run', () => {
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Connect HEx to Authentik' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Connect Authentik' })).toBeEnabled()
  })

  it('wires Authentik and offers sign-in on success', async () => {
    const fetchMock = mockUnlock({
      ok: true,
      status: 200,
      body: { ok: true, client_id: 'cid', provider_pk: 7 },
    })
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Connect Authentik' }))

    expect(fetchMock).toHaveBeenCalledWith(
      '/setup/wire',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(
      await screen.findByRole('heading', { name: 'HEx is connected to Authentik' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/auth/login')
  })

  it('shows a retryable message when Authentik is not ready yet (503)', async () => {
    mockUnlock({ ok: false, status: 503 })
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Connect Authentik' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/isn.t reachable yet/i)
  })

  it('shows a failure message when wiring fails (502)', async () => {
    mockUnlock({ ok: false, status: 502 })
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Connect Authentik' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t finish configuring/i)
  })

  it('shows a generic message on an unexpected wiring error', async () => {
    mockUnlock({ ok: false, status: 500 })
    render(<BootstrapGate phase="bootstrap" onAdvance={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Connect Authentik' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/something went wrong/i)
  })
})

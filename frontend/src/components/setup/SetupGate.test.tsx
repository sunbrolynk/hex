import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SetupGate } from './SetupGate'

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as unknown as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SetupGate', () => {
  it('renders children once setup is complete', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ok({ phase: 'complete', setup_required: false })),
    )
    render(
      <SetupGate>
        <div>owner dashboard</div>
      </SetupGate>,
    )
    expect(await screen.findByText('owner dashboard')).toBeInTheDocument()
  })

  it('fails closed with an alert when the status endpoint returns an error code', async () => {
    // e.g. 503 while the DB is still coming up — the app must stay gated, never fall through.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 503 }) as unknown as Response),
    )
    render(
      <SetupGate>
        <div>owner dashboard</div>
      </SetupGate>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t reach hex/i)
    expect(screen.queryByText('owner dashboard')).not.toBeInTheDocument()
  })

  it('keeps the app closed behind the gate, then reveals it after unlock re-checks status', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok({ phase: 'first_run', setup_required: true })) // initial status
      .mockResolvedValueOnce(ok({ phase: 'bootstrap', setup_required: true })) // unlock POST
      .mockResolvedValueOnce(ok({ phase: 'complete', setup_required: false })) // refresh status
    vi.stubGlobal('fetch', fetchMock)

    render(
      <SetupGate>
        <div>owner dashboard</div>
      </SetupGate>,
    )

    await screen.findByRole('heading', { name: 'Finish setting up HEx' })
    expect(screen.queryByText('owner dashboard')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Setup token'), { target: { value: 'a-real-token' } })
    fireEvent.click(screen.getByRole('button', { name: 'Begin setup' }))

    expect(await screen.findByText('owner dashboard')).toBeInTheDocument()
  })
})

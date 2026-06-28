import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { InviteAcceptPage } from './InviteAcceptPage'

function json(body: unknown, status = 200): Response {
  return { ok: status < 400, status, json: async () => body } as unknown as Response
}

const VALID = {
  requestable: ['plex'],
  grant_providers: ['jellyfin'],
  expires_at: '2030-01-01T00:00:00Z',
}

function renderPage(token = 'tok') {
  return render(
    <MemoryRouter initialEntries={[`/invite/${token}`]}>
      <Routes>
        <Route path="/invite/:token" element={<InviteAcceptPage />} />
      </Routes>
    </MemoryRouter>,
  )
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

describe('InviteAcceptPage', () => {
  it('renders 404 for an invalid invite', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({}, 404)),
    )
    renderPage()
    expect(await screen.findByRole('heading', { name: '404' })).toBeInTheDocument()
  })

  it('shows the invite and its granted services when valid', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(VALID)),
    )
    renderPage()
    expect(await screen.findByRole('heading', { name: /you’re invited/i })).toBeInTheDocument()
    expect(screen.getByText(/jellyfin/)).toBeInTheDocument()
  })

  it('redirects to the enrollment URL on accept', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string | URL, init?: RequestInit) =>
        (init?.method ?? 'GET').toUpperCase() === 'POST'
          ? json({ enroll_url: 'http://ak/enroll' })
          : json(VALID),
      ),
    )
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Accept & create account' }))
    await vi.waitFor(() => expect(window.location.assign).toHaveBeenCalledWith('http://ak/enroll'))
  })

  it.each([
    [404, /no longer valid/i],
    [429, /too many attempts/i],
    [503, /temporarily unavailable/i],
  ])('shows the right message when accept fails with %i', async (status, pattern) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string | URL, init?: RequestInit) =>
        (init?.method ?? 'GET').toUpperCase() === 'POST' ? json({}, status) : json(VALID),
      ),
    )
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Accept & create account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(pattern)
    expect(window.location.assign).not.toHaveBeenCalled()
  })

  it('renders 404 when the preview request errors (non-404)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network down')
      }),
    )
    renderPage()
    expect(await screen.findByRole('heading', { name: '404' })).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

function mockStatus(body: { phase: string; setup_required: boolean }) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => body }) as unknown as Response),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App shell', () => {
  beforeEach(() => mockStatus({ phase: 'complete', setup_required: false }))

  it('renders the home landing and a quiet About link once setup is complete', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: 'HEx' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'About' })).toHaveAttribute('href', '/about')
  })
})

describe('App gating', () => {
  it('shows the bootstrap gate while first-run setup is required', async () => {
    mockStatus({ phase: 'first_run', setup_required: true })
    render(<App />)
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Finish setting up HEx' }),
    ).toBeInTheDocument()
    // The real app surface must not be reachable behind the gate.
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

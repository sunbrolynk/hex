import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Tile } from '../../api/dashboard'
import { HomePage } from './HomePage'

function json(body: unknown, status = 200): Response {
  return { ok: status < 400, status, json: async () => body } as unknown as Response
}

const MEDIA: Tile = {
  provider_id: 'demo-media',
  name: 'Demo Media',
  category: 'media',
  state: 'granted',
  integration_mode: 'sso_group',
  url: 'https://media.demo.hex.local',
  seamless: true,
}

afterEach(() => vi.unstubAllGlobals())

describe('HomePage', () => {
  it('renders a tile as a deep-link to the service', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ tiles: [MEDIA] })),
    )
    render(<HomePage />)
    const link = await screen.findByRole('link', { name: /Demo Media/ })
    expect(link).toHaveAttribute('href', 'https://media.demo.hex.local')
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('renders a card without a link when the tile has no url', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ tiles: [{ ...MEDIA, url: null }] })),
    )
    render(<HomePage />)
    expect(await screen.findByRole('heading', { name: 'Demo Media' })).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('shows an empty state when the user has no services', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ tiles: [] })),
    )
    render(<HomePage />)
    expect(await screen.findByText(/don’t have access to any services/i)).toBeInTheDocument()
  })

  it('shows a loading state before the dashboard resolves', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => {})), // never resolves
    )
    render(<HomePage />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('falls back to the raw state for an unknown status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ tiles: [{ ...MEDIA, state: 'mystery' }] })),
    )
    render(<HomePage />)
    expect(await screen.findByText('mystery')).toBeInTheDocument()
  })

  it('treats a response with no tiles key as empty (no crash)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({})),
    )
    render(<HomePage />)
    expect(await screen.findByText(/don’t have access to any services/i)).toBeInTheDocument()
  })

  it('surfaces an error when the dashboard fails to load', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({}, 503)),
    )
    render(<HomePage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t load/i)
  })
})

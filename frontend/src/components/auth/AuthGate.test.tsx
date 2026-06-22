import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthGate } from './AuthGate'
import { useAuth } from './context'

type MeBody = { id: number; username: string | null; email: string | null; is_owner: boolean }
const USER: MeBody = { id: 1, username: 'owner', email: 'o@example.com', is_owner: true }

function mockFetch(handler: (url: string, init?: RequestInit) => Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init?: RequestInit) => handler(String(input), init)),
  )
}

function ok(body: unknown, status = 200): Response {
  return { ok: true, status, json: async () => body } as unknown as Response
}
function unauthorized(): Response {
  return { ok: false, status: 401, json: async () => ({}) } as unknown as Response
}

afterEach(() => vi.unstubAllGlobals())

describe('AuthGate', () => {
  it('renders children when a session exists', async () => {
    mockFetch(() => ok(USER))
    render(
      <AuthGate>
        <p>secret app</p>
      </AuthGate>,
    )
    expect(await screen.findByText('secret app')).toBeInTheDocument()
  })

  it('shows the login gate on 401', async () => {
    mockFetch(() => unauthorized())
    render(
      <AuthGate>
        <p>secret app</p>
      </AuthGate>,
    )
    expect(await screen.findByRole('button', { name: 'Log in with Authentik' })).toBeInTheDocument()
    expect(screen.queryByText('secret app')).not.toBeInTheDocument()
  })

  it('surfaces a non-blocking error when /auth/me is unreachable', async () => {
    mockFetch(() => {
      throw new Error('network down')
    })
    render(
      <AuthGate>
        <p>secret app</p>
      </AuthGate>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t reach hex/i)
  })

  it('logout revokes server-side and re-gates to the login screen', async () => {
    let signedIn = true
    mockFetch((url) => {
      if (url.includes('/auth/logout')) {
        signedIn = false
        return ok({}, 204)
      }
      return signedIn ? ok(USER) : unauthorized()
    })

    function Consumer() {
      const { logout } = useAuth()
      return (
        <button type="button" onClick={() => void logout()}>
          do logout
        </button>
      )
    }

    render(
      <AuthGate>
        <Consumer />
      </AuthGate>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'do logout' }))
    expect(await screen.findByRole('button', { name: 'Log in with Authentik' })).toBeInTheDocument()
  })
})

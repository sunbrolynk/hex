// Client for the session-cookie auth surface (same-origin BFF). No tokens touch the browser.

export interface CurrentUser {
  id: number
  username: string | null
  email: string | null
  is_owner: boolean
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  const res = await fetch('/auth/me')
  if (res.status === 401) return null // not signed in
  if (!res.ok) throw new Error(`auth/me ${res.status}`)
  return (await res.json()) as CurrentUser
}

export async function logout(): Promise<void> {
  await fetch('/auth/logout', { method: 'POST' })
}

// Login is a full-page navigation (the backend 302s to Authentik) — never a fetch.
export function startLogin(next = '/'): void {
  const path = next && next !== '/' ? `/auth/login?next=${encodeURIComponent(next)}` : '/auth/login'
  window.location.assign(path)
}

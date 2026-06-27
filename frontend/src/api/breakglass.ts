// Client for the LAN-only break-glass emergency surface. The page is reachable only on the
// break-glass listener; availability() confirms that before the form is shown, so the page reads as
// non-existent on the proxy-facing origin (the backend 404s both calls there).

export async function breakglassAvailable(): Promise<boolean> {
  try {
    const res = await fetch('/auth/breakglass')
    return res.ok
  } catch {
    return false
  }
}

export type BreakGlassResult =
  | { ok: true }
  | { ok: false; reason: 'invalid' | 'unavailable' | 'throttled' | 'error' }

// Authenticate the local owner credential. Status maps to a distinct, non-leaky reason: 401 any
// wrong factor, 403 Authentik reachable (use normal sign-in), 429 locked out, else generic error.
export async function breakglassLogin(
  username: string,
  password: string,
  totp: string,
): Promise<BreakGlassResult> {
  let res: Response
  try {
    res = await fetch('/auth/breakglass', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, totp }),
    })
  } catch {
    return { ok: false, reason: 'error' }
  }
  if (res.ok) return { ok: true }
  if (res.status === 401) return { ok: false, reason: 'invalid' }
  if (res.status === 403) return { ok: false, reason: 'unavailable' }
  if (res.status === 429) return { ok: false, reason: 'throttled' }
  return { ok: false, reason: 'error' }
}

import { type FormEvent, useEffect, useState } from 'react'
import { type BreakGlassResult, breakglassAvailable, breakglassLogin } from '../../api/breakglass'
import { NotFound } from '../notfound/NotFound'

// Emergency owner sign-in, served only on the LAN break-glass listener (ADR 0008). Independent of
// SetupGate/AuthGate — it must work precisely when Authentik (and so the normal login) is down.

const MESSAGES: Record<Exclude<BreakGlassResult, { ok: true }>['reason'], string> = {
  invalid: 'Those break-glass credentials weren’t accepted.',
  unavailable: 'Break-glass is unavailable while Authentik is reachable. Use normal sign-in.',
  throttled: 'Too many attempts. Wait a few minutes, then try again.',
  error: 'Something went wrong. Try again.',
}

export function BreakGlassLogin() {
  const [available, setAvailable] = useState<'loading' | 'yes' | 'no'>('loading')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    breakglassAvailable().then((ok) => setAvailable(ok ? 'yes' : 'no'))
  }, [])

  if (available === 'loading') return <p>Loading…</p>
  // Off the listener the probe 404s; render the same generic 404 as any unknown route, so the page
  // is indistinguishable from one that doesn't exist (the real boundary is the server-side listener).
  if (available === 'no') return <NotFound />

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    const result = await breakglassLogin(username, password, totp)
    if (result.ok) {
      // Full-page load so SetupGate/AuthGate re-run with the fresh break-glass session cookie.
      window.location.assign('/')
      return
    }
    setBusy(false)
    setError(MESSAGES[result.reason])
  }

  return (
    <section>
      <h1>Break-glass sign-in</h1>
      <p>Emergency owner access for when Authentik is unreachable. Every use is audited.</p>
      <form onSubmit={onSubmit}>
        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="off"
          />
        </label>
        <label>
          Passphrase
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="off"
          />
        </label>
        <label>
          Authenticator code
          <input
            value={totp}
            onChange={(e) => setTotp(e.target.value)}
            inputMode="numeric"
            autoComplete="off"
          />
        </label>
        <button type="submit" disabled={busy || !username || !password || !totp}>
          {busy ? 'Signing in…' : 'Break the glass'}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

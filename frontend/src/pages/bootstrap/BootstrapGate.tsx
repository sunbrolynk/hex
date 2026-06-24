import { type FormEvent, useEffect, useState } from 'react'
import { type CurrentUser, getCurrentUser } from '../../api/auth'
import { completeSetup, unlockSetup, wireAuthentik } from '../../api/setup'

// The seed of the owner-setup wizard (owner-setup-wizard-vision): the token gate, then the
// Authentik wiring step. Wrong/throttled/error all surface a generic, non-leaky line.
const MESSAGES: Record<'invalid' | 'throttled' | 'locked' | 'error', string> = {
  invalid: 'That setup token was not accepted. Re-check it in the server logs and try again.',
  throttled: 'Too many attempts. Wait a minute, then try again.',
  locked:
    'Setup is locked after too many failed attempts. Restart HEx to mint a new token, then enter that.',
  error: 'Something went wrong reaching HEx. Try again.',
}

const WIRE_MESSAGES: Record<'unavailable' | 'failed' | 'error', string> = {
  unavailable: 'Authentik isn’t reachable yet. Give it a moment, then try again.',
  failed: 'HEx couldn’t finish configuring Authentik. Check the Authentik logs and retry.',
  error: 'Something went wrong reaching HEx. Try again.',
}

interface Props {
  phase: string
  onAdvance: () => void
}

// After the token unlock, HEx finishes wiring Authentik and rotates onto its own scoped token.
// Phase stays "bootstrap" until owner setup (Slice 3b) completes; once wired, login is available.
function WireStep() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wired, setWired] = useState(false)

  async function onWire() {
    setBusy(true)
    setError(null)
    const result = await wireAuthentik()
    setBusy(false)
    if (result.ok) setWired(true)
    else setError(WIRE_MESSAGES[result.reason])
  }

  if (wired) {
    return (
      <section>
        <h1>HEx is connected to Authentik</h1>
        <p>Setup is wired and HEx is now using its own scoped credentials. Sign in to continue.</p>
        <a href="/auth/login">Sign in</a>
      </section>
    )
  }

  return (
    <section>
      <h1>Connect HEx to Authentik</h1>
      <p>
        HEx will finish configuring its Authentik integration and switch from the bootstrap token to
        its own least-privilege credentials.
      </p>
      <button type="button" onClick={onWire} disabled={busy}>
        {busy ? 'Connecting…' : 'Connect Authentik'}
      </button>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

// The final bootstrap step: the signed-in user claims ownership, which advances setup to COMPLETE.
// onComplete refreshes the gate, dropping the now-owner into the app.
function OwnerClaimStep({ user, onComplete }: { user: CurrentUser; onComplete: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onClaim() {
    setBusy(true)
    setError(null)
    const ok = await completeSetup()
    setBusy(false)
    if (ok) onComplete()
    else setError('Couldn’t finish setup. Reload HEx and try again.')
  }

  return (
    <section>
      <h1>Claim ownership of HEx</h1>
      <p>
        You’re signed in as <strong>{user.username ?? user.email ?? 'your account'}</strong>. Claim
        ownership to finish setup and open HEx.
      </p>
      <button type="button" onClick={onClaim} disabled={busy}>
        {busy ? 'Finishing…' : 'Claim ownership & finish'}
      </button>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

// In bootstrap mode, branch on whether the owner has signed in yet: anonymous → wire + sign in;
// signed in → claim ownership. The OIDC round-trip lands back here authenticated.
function BootstrapFlow({ onAdvance }: { onAdvance: () => void }) {
  const [user, setUser] = useState<CurrentUser | null | 'loading' | 'error'>('loading')

  useEffect(() => {
    // getCurrentUser returns null only on a clean 401 (anonymous → wire step). Any other failure
    // (5xx, network) must surface as an error, not masquerade as "signed out" and bounce an
    // already-authenticated owner back to the wiring step.
    getCurrentUser().then(
      (u) => setUser(u),
      () => setUser('error'),
    )
  }, [])

  if (user === 'loading') return <p>Loading HEx…</p>
  if (user === 'error') {
    return <p role="alert">Couldn’t reach HEx. Check the server is running and reload.</p>
  }
  if (user === null) return <WireStep />
  return <OwnerClaimStep user={user} onComplete={onAdvance} />
}

export function BootstrapGate({ phase, onAdvance }: Props) {
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Past first run the token is spent; wiring + owner claim take over.
  if (phase !== 'first_run') {
    return <BootstrapFlow onAdvance={onAdvance} />
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    const result = await unlockSetup(token)
    setBusy(false)
    if (result.ok) onAdvance()
    else setError(MESSAGES[result.reason])
  }

  return (
    <section>
      <h1>Finish setting up HEx</h1>
      <p>
        On first start HEx printed a one-time <strong>setup token</strong> to its container logs.
        Retrieve it from the host and enter it below to begin.
      </p>
      <form onSubmit={onSubmit}>
        <label htmlFor="setup-token">Setup token</label>
        <input
          id="setup-token"
          name="token"
          autoComplete="off"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || token.length === 0}>
          {busy ? 'Checking…' : 'Begin setup'}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

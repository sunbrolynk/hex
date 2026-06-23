import { type FormEvent, useState } from 'react'
import { unlockSetup, wireAuthentik } from '../../api/setup'

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

export function BootstrapGate({ phase, onAdvance }: Props) {
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Past first run the token is spent; the wiring step takes over.
  if (phase !== 'first_run') {
    return <WireStep />
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

import { type FormEvent, useState } from 'react'
import { unlockSetup } from '../../api/setup'

// The seed of the owner-setup wizard (owner-setup-wizard-vision): for now, the token gate plus a
// stub for what comes after unlock. Wrong/throttled/error all surface a generic, non-leaky line.
const MESSAGES: Record<'invalid' | 'throttled' | 'error', string> = {
  invalid: 'That setup token was not accepted. Re-check it in the server logs and try again.',
  throttled: 'Too many attempts. Wait a minute, then try again.',
  error: 'Something went wrong reaching HEx. Try again.',
}

interface Props {
  phase: string
  onAdvance: () => void
}

export function BootstrapGate({ phase, onAdvance }: Props) {
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Past first run the token is spent; owner setup (Authentik wiring) lands here in Slice 3.
  if (phase !== 'first_run') {
    return (
      <section>
        <h1>Setup unlocked</h1>
        <p>HEx is in bootstrap mode. Owner setup continues here.</p>
      </section>
    )
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

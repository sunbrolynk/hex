import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  type AcceptResult,
  type InvitePreview,
  acceptInvite,
  previewInvite,
} from '../../api/invites'
import { NotFound } from '../notfound/NotFound'

// Public invite-acceptance landing (gate-free, like /breakglass). Shows what the invite grants,
// then on accept redirects to the Authentik enrollment flow where the user sets their own password
// (Authentik is the identity SoT). Invalid/expired/revoked invites read as Not Found.

const MESSAGES: Record<Exclude<AcceptResult, { ok: true }>['reason'], string> = {
  gone: 'This invite is no longer valid.',
  throttled: 'Too many attempts. Wait a moment and try again.',
  unavailable: 'Sign-up is temporarily unavailable. Try again shortly.',
  error: 'Something went wrong. Try again.',
}

export function InviteAcceptPage() {
  const { token = '' } = useParams()
  const [state, setState] = useState<'loading' | 'invalid' | InvitePreview>('loading')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    previewInvite(token).then(
      (preview) => setState(preview ?? 'invalid'),
      () => setState('invalid'),
    )
  }, [token])

  useEffect(() => load(), [load])

  if (state === 'loading') return <p>Loading…</p>
  if (state === 'invalid') return <NotFound />

  async function onAccept() {
    setBusy(true)
    setError(null)
    const result = await acceptInvite(token)
    if (result.ok) {
      window.location.assign(result.enroll_url) // off to Authentik enrollment
      return
    }
    setBusy(false)
    setError(MESSAGES[result.reason])
  }

  return (
    <section>
      <h1>You’re invited to HEx</h1>
      <p>Create your account to get access. You’ll set your password on the next screen.</p>
      {state.grant_providers.length > 0 && (
        <p>Includes access to: {state.grant_providers.join(', ')}</p>
      )}
      <button type="button" onClick={() => void onAccept()} disabled={busy}>
        {busy ? 'Starting…' : 'Accept & create account'}
      </button>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

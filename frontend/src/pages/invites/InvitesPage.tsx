import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { type Invite, createInvite, listInvites, revokeInvite } from '../../api/invites'
import { useAuth } from '../../components/auth/context'

// Owner-only invite management. Authorization is enforced server-side (require_owner); this also
// hides itself for non-owners as a courtesy. Slice 6-1 — acceptance/signup lands in 6-2.

export function InvitesPage() {
  const { user } = useAuth()
  const [invites, setInvites] = useState<Invite[]>([])
  const [ttl, setTtl] = useState(168)
  const [requestable, setRequestable] = useState('')
  const [link, setLink] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = useCallback(() => {
    listInvites().then(setInvites, () => setError('Couldn’t load invites.'))
  }, [])

  useEffect(() => {
    if (user.is_owner) reload()
  }, [user.is_owner, reload])

  if (!user.is_owner) return <p>Owner only.</p>

  async function onCreate(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const invite = await createInvite({
        ttl_hours: ttl,
        requestable: requestable
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      })
      setLink(`${window.location.origin}/invite/${invite.token}`)
      reload()
    } catch {
      setError('Couldn’t create the invite.')
    }
    setBusy(false)
  }

  async function onRevoke(id: number) {
    try {
      await revokeInvite(id)
      reload()
    } catch {
      setError('Couldn’t revoke that invite.')
    }
  }

  return (
    <section>
      <h1>Invites</h1>
      <form onSubmit={onCreate}>
        <label>
          Expires in (hours)
          <input
            type="number"
            min={1}
            value={ttl}
            onChange={(e) => setTtl(Number(e.target.value))}
          />
        </label>
        <label>
          Requestable services (comma-separated)
          <input value={requestable} onChange={(e) => setRequestable(e.target.value)} />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? 'Creating…' : 'Create invite'}
        </button>
      </form>
      {link && (
        <p>
          Invite link (copy it now — shown once): <code>{link}</code>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <ul>
        {invites.map((invite) => (
          <li key={invite.id}>
            #{invite.id} — {invite.status} — expires {new Date(invite.expires_at).toLocaleString()}
            {invite.status === 'active' && (
              <button type="button" onClick={() => void onRevoke(invite.id)}>
                Revoke
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

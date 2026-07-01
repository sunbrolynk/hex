import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { type Invite, createInvite, listInvites, revokeInvite } from '../../api/invites'
import { type Provider, getProviders } from '../../api/providers'
import { useAuth } from '../../components/auth/context'

// Owner-only invite management. Authorization is enforced server-side (require_owner); this also
// hides itself for non-owners as a courtesy. The owner grants/offers services from a selectable
// list (never free text) — a picked tier KEY resolves to the structured grant server-side (ADR 0015).

export function InvitesPage() {
  const { user } = useAuth()
  const [invites, setInvites] = useState<Invite[]>([])
  const [providers, setProviders] = useState<Provider[] | null>(null)
  const [ttl, setTtl] = useState(24)
  const [grantTiers, setGrantTiers] = useState<Record<string, string>>({}) // provider_id -> tier key
  const [requestable, setRequestable] = useState<string[]>([])
  const [link, setLink] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = useCallback(() => {
    listInvites().then(setInvites, () => setError('Couldn’t load invites.'))
  }, [])

  useEffect(() => {
    if (!user.is_owner) return
    reload()
    getProviders().then(setProviders, () => setError('Couldn’t load services.'))
  }, [user.is_owner, reload])

  if (!user.is_owner) return <p>Owner only.</p>

  function toggleGrant(p: Provider) {
    setGrantTiers((cur) => {
      const next = { ...cur }
      if (p.id in next) delete next[p.id]
      else next[p.id] = p.tiers[0]?.key ?? ''
      return next
    })
  }

  function toggleRequestable(id: string) {
    setRequestable((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const invite = await createInvite({ ttl_hours: ttl, requestable, default_grants: grantTiers })
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

        <fieldset>
          <legend>Services</legend>
          {providers === null && <p>Loading services…</p>}
          {providers !== null && providers.length === 0 && (
            <p>No services available to grant yet.</p>
          )}
          {providers?.map((p) => {
            const granted = p.id in grantTiers
            return (
              <div key={p.id}>
                <label>
                  <input type="checkbox" checked={granted} onChange={() => toggleGrant(p)} />
                  Grant {p.name} <small>({p.category})</small>
                </label>
                {granted && p.tiers.length > 0 && (
                  <label>
                    Tier
                    <select
                      value={grantTiers[p.id]}
                      onChange={(e) => setGrantTiers((cur) => ({ ...cur, [p.id]: e.target.value }))}
                    >
                      {p.tiers.map((t) => (
                        <option key={t.key} value={t.key}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label>
                  <input
                    type="checkbox"
                    checked={requestable.includes(p.id)}
                    onChange={() => toggleRequestable(p.id)}
                  />
                  Requestable later
                </label>
              </div>
            )
          })}
        </fieldset>

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

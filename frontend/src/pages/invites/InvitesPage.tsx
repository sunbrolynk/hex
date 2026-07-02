import { type FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { type Invite, createInvite, listInvites, revokeInvite } from '../../api/invites'
import { type Provider, getProviders } from '../../api/providers'
import { useAuth } from '../../components/auth/context'

// Owner-only invite management. Authorization is enforced server-side (require_owner); this also
// hides itself for non-owners as a courtesy. The owner adds services from a dropdown (never free
// text) into a list, choosing per service whether it's granted now or requestable later — services
// left off the list stay hidden (ADR 0015 granted/visible/hidden). A picked tier key resolves to
// the structured grant server-side; a level picker shows only when a provider offers a choice.

type Mode = 'grant' | 'requestable'
interface Selection {
  mode: Mode
  tier: string
}

export function InvitesPage() {
  const { user } = useAuth()
  const [invites, setInvites] = useState<Invite[]>([])
  const [providers, setProviders] = useState<Provider[] | null>(null)
  const [ttl, setTtl] = useState(24)
  const [selected, setSelected] = useState<Record<string, Selection>>({}) // provider_id -> choice
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

  const byId = useMemo(
    () => Object.fromEntries((providers ?? []).map((p) => [p.id, p])),
    [providers],
  )
  const available = (providers ?? []).filter((p) => !(p.id in selected))

  if (!user.is_owner) return <p>Owner only.</p>

  function addService(id: string) {
    const p = byId[id]
    if (!p) return
    setSelected((cur) => ({ ...cur, [id]: { mode: 'grant', tier: p.tiers[0]?.key ?? '' } }))
  }
  function removeService(id: string) {
    setSelected((cur) => {
      const next = { ...cur }
      delete next[id]
      return next
    })
  }
  function update(id: string, patch: Partial<Selection>) {
    setSelected((cur) => ({ ...cur, [id]: { ...cur[id], ...patch } }))
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    const default_grants: Record<string, string> = {}
    const requestable: string[] = []
    for (const [id, sel] of Object.entries(selected)) {
      if (sel.mode === 'grant') default_grants[id] = sel.tier
      else requestable.push(id)
    }
    try {
      const invite = await createInvite({ ttl_hours: ttl, requestable, default_grants })
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
          {providers !== null &&
            (available.length > 0 ? (
              <label>
                Add a service
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value) addService(e.target.value)
                  }}
                >
                  <option value="">Choose a service…</option>
                  {available.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.category})
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              providers.length === 0 && <p>No services available yet.</p>
            ))}

          <ul>
            {Object.entries(selected).map(([id, sel]) => {
              const p = byId[id]
              if (!p) return null
              return (
                <li key={id}>
                  <span>
                    {p.name} <small>({p.category})</small>
                  </span>
                  <label>
                    <input
                      type="radio"
                      name={`mode-${id}`}
                      checked={sel.mode === 'grant'}
                      onChange={() => update(id, { mode: 'grant' })}
                    />
                    Grant now
                  </label>
                  <label>
                    <input
                      type="radio"
                      name={`mode-${id}`}
                      checked={sel.mode === 'requestable'}
                      onChange={() => update(id, { mode: 'requestable' })}
                    />
                    Requestable later
                  </label>
                  {sel.mode === 'grant' && p.tiers.length > 1 && (
                    <label>
                      Level
                      <select
                        value={sel.tier}
                        onChange={(e) => update(id, { tier: e.target.value })}
                      >
                        {p.tiers.map((t) => (
                          <option key={t.key} value={t.key}>
                            {t.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <button type="button" onClick={() => removeService(id)}>
                    Remove
                  </button>
                </li>
              )
            })}
          </ul>
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

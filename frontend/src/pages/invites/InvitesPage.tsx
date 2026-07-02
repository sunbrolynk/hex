import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  type Invite,
  type RecipientKind,
  createInvite,
  listInvites,
  revokeInvite,
} from '../../api/invites'
import { type Provider, getProviders } from '../../api/providers'
import { useAuth } from '../../components/auth/context'

// Owner-only invite management. Authorization is enforced server-side (require_owner); this also
// hides itself for non-owners as a courtesy. The owner optionally names a recipient ("who" —
// validated/normalized server-side, never trusted from here) and adds services from a dropdown
// (never free text) into a list, choosing per service grant-now vs requestable-later; services left
// off stay hidden (ADR 0015). The history below is an immutable, paginated record.

type Mode = 'grant' | 'requestable'
interface Selection {
  mode: Mode
  tier: string
}

const PER_PAGE_OPTIONS = [10, 25, 50]
const RECIPIENT_KINDS: { value: RecipientKind; label: string; type: string }[] = [
  { value: 'email', label: 'Email', type: 'email' },
  { value: 'phone', label: 'Phone', type: 'tel' },
  { value: 'label', label: 'Label', type: 'text' },
]

export function InvitesPage() {
  const { user } = useAuth()
  const [invites, setInvites] = useState<Invite[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [perPage, setPerPage] = useState(25)
  const [reloadKey, setReloadKey] = useState(0)
  const [providers, setProviders] = useState<Provider[] | null>(null)
  const [ttl, setTtl] = useState(24)
  const [selected, setSelected] = useState<Record<string, Selection>>({}) // provider_id -> choice
  const [recipientKind, setRecipientKind] = useState<'' | RecipientKind>('')
  const [recipient, setRecipient] = useState('')
  const [createOpen, setCreateOpen] = useState(true)
  const [historyOpen, setHistoryOpen] = useState(true)
  const [link, setLink] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const formRef = useRef<HTMLFormElement>(null)
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    if (!user.is_owner) return
    listInvites({ limit: perPage, offset }).then(
      (page) => {
        setInvites(page.items)
        setTotal(page.total)
      },
      () => setError('Couldn’t load invites.'),
    )
  }, [user.is_owner, perPage, offset, reloadKey])

  useEffect(() => {
    if (!user.is_owner) return
    getProviders().then(setProviders, () => setError('Couldn’t load services.'))
  }, [user.is_owner])

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

  async function onCreate(addAnother: boolean) {
    setBusy(true)
    setError(null)
    const default_grants: Record<string, string> = {}
    const requestable: string[] = []
    for (const [id, sel] of Object.entries(selected)) {
      if (sel.mode === 'grant') default_grants[id] = sel.tier
      else requestable.push(id)
    }
    try {
      const invite = await createInvite({
        ttl_hours: ttl,
        requestable,
        default_grants,
        ...(recipientKind ? { recipient, recipient_kind: recipientKind } : {}),
      })
      setLink(`${window.location.origin}/invite/${invite.token}`)
      setSelected({})
      setRecipient('')
      setRecipientKind('')
      setOffset(0) // the new invite is newest → surface it on page 1
      reload()
      if (!addAnother) setCreateOpen(false)
    } catch {
      setError(
        recipientKind
          ? `Couldn’t create the invite — is that a valid ${recipientKind}?`
          : 'Couldn’t create the invite.',
      )
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

  const pageCount = Math.max(1, Math.ceil(total / perPage))
  const currentPage = Math.floor(offset / perPage) + 1

  return (
    <section>
      <h1>Invites</h1>

      <details
        open={createOpen}
        onToggle={(e) => setCreateOpen((e.currentTarget as HTMLDetailsElement).open)}
      >
        <summary>New invitation</summary>
        <form
          ref={formRef}
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            void onCreate(false)
          }}
        >
          <fieldset>
            <legend>Recipient</legend>
            <label>
              Recipient type
              <select
                value={recipientKind}
                onChange={(e) => {
                  setRecipientKind(e.target.value as '' | RecipientKind)
                  setRecipient('') // a value valid for one kind isn't for another
                }}
              >
                <option value="">None (share the link yourself)</option>
                {RECIPIENT_KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
            </label>
            {recipientKind && (
              <label>
                Recipient
                <input
                  type={RECIPIENT_KINDS.find((k) => k.value === recipientKind)?.type ?? 'text'}
                  value={recipient}
                  required
                  onChange={(e) => setRecipient(e.target.value)}
                />
              </label>
            )}
          </fieldset>

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
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (formRef.current?.reportValidity() === false) return // enforce required/type
              void onCreate(true)
            }}
          >
            Create &amp; add another
          </button>
        </form>
      </details>

      {link && (
        <p>
          Invite link (copy it now — shown once): <code>{link}</code>
        </p>
      )}
      {error && <p role="alert">{error}</p>}

      <details
        open={historyOpen}
        onToggle={(e) => setHistoryOpen((e.currentTarget as HTMLDetailsElement).open)}
      >
        <summary>Invitation history ({total})</summary>
        <ul>
          {invites.map((invite) => (
            <li key={invite.id}>
              #{invite.id} — {invite.status}
              {invite.recipient
                ? ` — ${invite.recipient_kind}: ${invite.recipient}`
                : ' — link only'}
              {invite.grant_providers.length > 0 &&
                ` — grants: ${invite.grant_providers.join(', ')}`}
              {invite.requestable.length > 0 && ` — requestable: ${invite.requestable.join(', ')}`}
              {' — expires '}
              {new Date(invite.expires_at).toLocaleString()}
              {invite.status === 'active' && (
                <button type="button" onClick={() => void onRevoke(invite.id)}>
                  Revoke
                </button>
              )}
            </li>
          ))}
        </ul>
        <div>
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - perPage))}
          >
            Previous
          </button>
          <span>
            Page {currentPage} of {pageCount}
          </span>
          <button
            type="button"
            disabled={offset + perPage >= total}
            onClick={() => setOffset(offset + perPage)}
          >
            Next
          </button>
          <label>
            Per page
            <select
              value={perPage}
              onChange={(e) => {
                setPerPage(Number(e.target.value))
                setOffset(0)
              }}
            >
              {PER_PAGE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
      </details>
    </section>
  )
}

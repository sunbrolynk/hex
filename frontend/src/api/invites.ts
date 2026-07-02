// Owner-only invite management (BFF; the backend enforces require_owner). The raw token comes back
// exactly once on creation — the UI surfaces it as a one-time link.

export type RecipientKind = 'email' | 'phone' | 'label'

export interface Invite {
  id: number
  status: string
  requestable: string[]
  grant_providers: string[]
  recipient: string | null
  recipient_kind: string | null
  created_at: string
  expires_at: string
  accepted_at: string | null
  revoked_at: string | null
}

export interface InvitePage {
  items: Invite[]
  total: number
  limit: number
  offset: number
}

export interface CreatedInvite {
  id: number
  token: string
  expires_at: string
}

export async function listInvites(params: { limit: number; offset: number }): Promise<InvitePage> {
  const q = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) })
  const res = await fetch(`/invites?${q}`)
  if (!res.ok) throw new Error(`invites ${res.status}`)
  return (await res.json()) as InvitePage
}

export async function createInvite(input: {
  ttl_hours: number
  requestable: string[]
  default_grants?: Record<string, string> // provider_id -> tier key (server resolves to the grant)
  recipient?: string // owner-only "who"; server validates + normalizes per kind
  recipient_kind?: RecipientKind
}): Promise<CreatedInvite> {
  const res = await fetch('/invites', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw new Error(`create ${res.status}`)
  return (await res.json()) as CreatedInvite
}

export async function revokeInvite(id: number): Promise<void> {
  const res = await fetch(`/invites/${id}/revoke`, { method: 'POST' })
  if (!res.ok) throw new Error(`revoke ${res.status}`)
}

// --- Public acceptance surface (the invited user, no session yet) ---

export interface InvitePreview {
  requestable: string[]
  grant_providers: string[]
  expires_at: string
}

// null = invalid/expired/revoked/unknown (uniform 404); throws only on an unexpected error.
export async function previewInvite(token: string): Promise<InvitePreview | null> {
  const res = await fetch(`/invite/${token}/preview`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`preview ${res.status}`)
  return (await res.json()) as InvitePreview
}

export type AcceptResult =
  | { ok: true; enroll_url: string }
  | { ok: false; reason: 'gone' | 'throttled' | 'unavailable' | 'error' }

// On success the caller redirects to enroll_url (Authentik enrollment). Status → reason:
// 404 gone (spent/expired), 429 throttled, 503 enrollment unavailable, else generic error.
export async function acceptInvite(token: string): Promise<AcceptResult> {
  let res: Response
  try {
    res = await fetch(`/invite/${token}/accept`, { method: 'POST' })
  } catch {
    return { ok: false, reason: 'error' }
  }
  if (res.ok)
    return { ok: true, enroll_url: ((await res.json()) as { enroll_url: string }).enroll_url }
  if (res.status === 404) return { ok: false, reason: 'gone' }
  if (res.status === 429) return { ok: false, reason: 'throttled' }
  if (res.status === 503) return { ok: false, reason: 'unavailable' }
  return { ok: false, reason: 'error' }
}

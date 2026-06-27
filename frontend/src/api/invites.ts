// Owner-only invite management (BFF; the backend enforces require_owner). The raw token comes back
// exactly once on creation — the UI surfaces it as a one-time link.

export interface Invite {
  id: number
  status: string
  requestable: string[]
  grant_providers: string[]
  created_at: string
  expires_at: string
  accepted_at: string | null
  revoked_at: string | null
}

export interface CreatedInvite {
  id: number
  token: string
  expires_at: string
}

export async function listInvites(): Promise<Invite[]> {
  const res = await fetch('/invites')
  if (!res.ok) throw new Error(`invites ${res.status}`)
  return (await res.json()) as Invite[]
}

export async function createInvite(input: {
  ttl_hours: number
  requestable: string[]
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

// Client for the unauthenticated first-run setup surface (same-origin BFF).

export interface SetupStatus {
  phase: string
  setup_required: boolean
}

export type UnlockResult =
  | { ok: true; status: SetupStatus }
  | { ok: false; reason: 'invalid' | 'throttled' | 'locked' | 'error' }

export async function getSetupStatus(): Promise<SetupStatus> {
  const res = await fetch('/setup/status')
  if (!res.ok) throw new Error(`setup status ${res.status}`)
  return (await res.json()) as SetupStatus
}

export async function unlockSetup(token: string): Promise<UnlockResult> {
  const res = await fetch('/setup/unlock', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (res.ok) return { ok: true, status: (await res.json()) as SetupStatus }
  // A wrong, expired, or already-consumed token are indistinguishable here, by design.
  if (res.status === 401) return { ok: false, reason: 'invalid' }
  if (res.status === 429) return { ok: false, reason: 'throttled' }
  // 423: lockout burned the token and froze setup until a restart re-mints.
  if (res.status === 423) return { ok: false, reason: 'locked' }
  return { ok: false, reason: 'error' }
}

export type WireResult =
  | { ok: true; clientId: string }
  | { ok: false; reason: 'unavailable' | 'failed' | 'error' }

// Trigger first-run Authentik wiring. The server holds all secrets; only the public client_id
// comes back. 503 = Authentik not ready yet (retry); 502 = wiring failed.
export async function wireAuthentik(): Promise<WireResult> {
  const res = await fetch('/setup/wire', { method: 'POST' })
  if (res.ok) {
    const body = (await res.json()) as { client_id: string }
    return { ok: true, clientId: body.client_id }
  }
  if (res.status === 503) return { ok: false, reason: 'unavailable' }
  if (res.status === 502) return { ok: false, reason: 'failed' }
  return { ok: false, reason: 'error' }
}

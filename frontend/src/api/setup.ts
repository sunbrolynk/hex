// Client for the unauthenticated first-run setup surface (same-origin BFF).

export interface SetupStatus {
  phase: string
  setup_required: boolean
}

export type UnlockResult =
  | { ok: true; status: SetupStatus }
  | { ok: false; reason: 'invalid' | 'throttled' | 'error' }

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
  return { ok: false, reason: 'error' }
}

// Owner-only catalog of grantable services + their tiers (drives the invite-create picker). The
// owner selects a tier KEY; the server holds the structured grant it resolves to.

export interface TierOption {
  key: string
  label: string
  description: string | null
}

export interface Provider {
  id: string
  name: string
  category: string
  integration_mode: string
  tiers: TierOption[]
}

export async function getProviders(): Promise<Provider[]> {
  const res = await fetch('/providers')
  if (!res.ok) throw new Error(`providers ${res.status}`)
  return (await res.json()) as Provider[]
}

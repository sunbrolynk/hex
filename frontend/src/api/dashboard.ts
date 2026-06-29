// Client for the per-user dashboard (same-origin BFF). Tiles are strictly the signed-in user's own
// grants — the server scopes them; the browser only renders what it is handed.

export interface Tile {
  provider_id: string
  name: string
  category: string
  state: string
  integration_mode: string
  url: string | null
  seamless: boolean
}

export async function getDashboard(): Promise<Tile[]> {
  const res = await fetch('/dashboard')
  if (!res.ok) throw new Error(`dashboard ${res.status}`)
  return ((await res.json()) as { tiles?: Tile[] }).tiles ?? []
}

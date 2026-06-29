import { useEffect, useState } from 'react'
import { type Tile, getDashboard } from '../../api/dashboard'

// The personalized dashboard: a read-only grid of the services this user has been granted, derived
// server-side from the ledger. Layout/drag-drop (6-4b) and theming (6-4c) build on this. Per ADR
// 0014 v1 has no user-authored code/CSS.

const STATE_LABELS: Record<string, string> = {
  granted: 'Active',
  pending_manual: 'Pending setup',
  pending_external_claim: 'Action needed',
  partial: 'Partial',
}

function TileCard({ tile }: { tile: Tile }) {
  const label = STATE_LABELS[tile.state] ?? tile.state
  const body = (
    <>
      <h3>{tile.name}</h3>
      <p>{tile.category}</p>
      <span aria-label={`status: ${label}`}>{label}</span>
    </>
  )
  // A configured deep-link makes the whole tile a link to the service; otherwise it's a plain card.
  return (
    <li>
      {tile.url ? (
        <a href={tile.url} rel="noreferrer">
          {body}
        </a>
      ) : (
        body
      )}
    </li>
  )
}

export function HomePage() {
  const [tiles, setTiles] = useState<Tile[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    getDashboard().then(
      (t) => active && setTiles(t),
      () => active && setError(true),
    )
    return () => {
      active = false
    }
  }, [])

  return (
    <section>
      <h1>Your services</h1>
      {error && <p role="alert">Couldn’t load your dashboard.</p>}
      {!error && tiles === null && <p>Loading…</p>}
      {!error && tiles !== null && tiles.length === 0 && (
        <p>You don’t have access to any services yet.</p>
      )}
      {tiles !== null && tiles.length > 0 && (
        <ul>
          {tiles.map((tile) => (
            <TileCard key={tile.provider_id} tile={tile} />
          ))}
        </ul>
      )}
    </section>
  )
}

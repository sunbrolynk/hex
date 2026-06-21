import { type ReactNode, useCallback, useEffect, useState } from 'react'
import { getSetupStatus, type SetupStatus } from '../../api/setup'
import { BootstrapGate } from '../../pages/bootstrap/BootstrapGate'

type State = { kind: 'loading' } | { kind: 'error' } | { kind: 'ready'; status: SetupStatus }

/** Fronts the whole app: while setup is required, only the bootstrap surface is reachable. */
export function SetupGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: 'loading' })

  const load = useCallback(() => {
    getSetupStatus().then(
      (status) => setState({ kind: 'ready', status }),
      () => setState({ kind: 'error' }),
    )
  }, [])

  // Re-check after the gate advances the phase; shows the spinner during the refetch.
  const refresh = useCallback(() => {
    setState({ kind: 'loading' })
    load()
  }, [load])

  useEffect(() => load(), [load])

  if (state.kind === 'loading') return <p>Loading HEx…</p>
  if (state.kind === 'error') {
    return <p role="alert">Couldn’t reach HEx. Check the server is running and reload.</p>
  }
  if (state.status.setup_required) {
    return <BootstrapGate phase={state.status.phase} onAdvance={refresh} />
  }
  return <>{children}</>
}

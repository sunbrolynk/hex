import { type ReactNode, useCallback, useEffect, useState } from 'react'
import { type CurrentUser, getCurrentUser, logout as apiLogout } from '../../api/auth'
import { AuthContext } from './context'
import { LoginGate } from './LoginGate'

type State =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'anonymous' }
  | { kind: 'authenticated'; user: CurrentUser }

/** Gates the app on a valid session (after setup). Anonymous → login; else provides the user. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: 'loading' })

  const load = useCallback(() => {
    getCurrentUser().then(
      (user) => setState(user ? { kind: 'authenticated', user } : { kind: 'anonymous' }),
      () => setState({ kind: 'error' }),
    )
  }, [])

  useEffect(() => load(), [load])

  const logout = useCallback(async () => {
    await apiLogout()
    setState({ kind: 'loading' })
    load()
  }, [load])

  if (state.kind === 'loading') return <p>Loading HEx…</p>
  if (state.kind === 'error') {
    return <p role="alert">Couldn’t reach HEx. Check the server is running and reload.</p>
  }
  if (state.kind === 'anonymous') return <LoginGate />
  return (
    <AuthContext.Provider value={{ user: state.user, logout }}>{children}</AuthContext.Provider>
  )
}

import { createContext, useContext } from 'react'
import type { CurrentUser } from '../../api/auth'

export interface AuthValue {
  user: CurrentUser
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthValue | null>(null)

/** The signed-in user + a logout action. Only valid beneath an authenticated `AuthGate`. */
export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (value === null) {
    throw new Error('useAuth must be used within an authenticated AuthGate')
  }
  return value
}

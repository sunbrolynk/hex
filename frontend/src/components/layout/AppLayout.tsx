import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/context'

/** App shell. The footer carries the quiet About/GitHub links (ADR 0012). */
export function AppLayout() {
  const { user, logout } = useAuth()
  return (
    <div className="app">
      <header>
        <span>{user.username ?? user.email ?? 'Signed in'}</span>
        {user.is_owner && <Link to="/invites">Invites</Link>}
        <button type="button" onClick={() => void logout()}>
          Log out
        </button>
      </header>
      <main>
        <Outlet />
      </main>
      <footer>
        <a href="https://github.com/sunbrolynk/hex">GitHub</a>
        <Link to="/about">About</Link>
      </footer>
    </div>
  )
}

import { Link, Outlet } from 'react-router-dom'

/** App shell. The footer carries the quiet About/GitHub links (ADR 0012). */
export function AppLayout() {
  return (
    <div className="app">
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

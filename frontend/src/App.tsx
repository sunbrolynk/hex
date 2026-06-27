import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom'
import { AuthGate } from './components/auth/AuthGate'
import { AppLayout } from './components/layout/AppLayout'
import { SetupGate } from './components/setup/SetupGate'
import { AboutPage } from './pages/about/AboutPage'
import { BreakGlassLogin } from './pages/breakglass/BreakGlassLogin'
import { HomePage } from './pages/home/HomePage'
import { InvitesPage } from './pages/invites/InvitesPage'
import { NotFound } from './pages/notfound/NotFound'

// The normal app sits behind setup + auth gates. Break-glass is deliberately outside them: it must
// render when Authentik (hence the normal login) is down — that's the whole point (ADR 0008).
function GatedApp() {
  return (
    <SetupGate>
      <AuthGate>
        <Outlet />
      </AuthGate>
    </SetupGate>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/breakglass" element={<BreakGlassLogin />} />
        <Route element={<GatedApp />}>
          <Route element={<AppLayout />}>
            <Route index element={<HomePage />} />
            <Route path="invites" element={<InvitesPage />} />
            <Route path="about" element={<AboutPage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  )
}

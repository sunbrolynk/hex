import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthGate } from './components/auth/AuthGate'
import { AppLayout } from './components/layout/AppLayout'
import { SetupGate } from './components/setup/SetupGate'
import { AboutPage } from './pages/about/AboutPage'
import { HomePage } from './pages/home/HomePage'

export function App() {
  return (
    <SetupGate>
      <AuthGate>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<HomePage />} />
              <Route path="about" element={<AboutPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthGate>
    </SetupGate>
  )
}

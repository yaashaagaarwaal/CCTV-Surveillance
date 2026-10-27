import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import FullScreenSpinner from './components/FullScreenSpinner'
import { useAuth } from './hooks/useAuth'
import AlertsPage from './pages/AlertsPage'
import CamerasPage from './pages/CamerasPage'
import DashboardPage from './pages/DashboardPage'
import EventsPage from './pages/EventsPage'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import PeoplePage from './pages/PeoplePage'
import RecordingsPage from './pages/RecordingsPage'
import UsersPage from './pages/UsersPage'

// Everything behind the login. Until the server has confirmed the session
// (AuthProvider asks /api/auth/me on every page load) nothing is rendered and
// no other API call is made; without a session the visitor goes to /login and
// is brought back to the page they asked for afterwards.
function RequireAuth({ children }) {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <FullScreenSpinner />
  if (status !== 'authenticated') return <Navigate to="/login" replace state={{ from: location }} />
  return children
}

// Hiding admin pages is a convenience; the server enforces roles on every request.
function RequireAdmin({ children }) {
  const { isAdmin } = useAuth()
  return isAdmin ? children : <Navigate to="/dashboard" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="cameras" element={<CamerasPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="recordings" element={<RecordingsPage />} />
        <Route path="people" element={<PeoplePage />} />
        <Route
          path="users"
          element={
            <RequireAdmin>
              <UsersPage />
            </RequireAdmin>
          }
        />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

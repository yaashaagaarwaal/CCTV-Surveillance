import { Route, Routes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import { Spinner } from './components/ui'
import { useAuth } from './hooks/useAuth'
import AlertsPage from './pages/AlertsPage'
import CamerasPage from './pages/CamerasPage'
import DashboardPage from './pages/DashboardPage'
import EventsPage from './pages/EventsPage'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import PeoplePage from './pages/PeoplePage'
import RecordingsPage from './pages/RecordingsPage'
import UsersPage from './pages/UsersPage'

export default function App() {
  const { status, isAdmin } = useAuth()

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <Spinner className="h-8 w-8" />
      </div>
    )
  }
  // Nothing of the dashboard is rendered (and no API call is made) until signed in.
  if (status !== 'authenticated') return <LoginPage />

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="cameras" element={<CamerasPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="recordings" element={<RecordingsPage />} />
        <Route path="people" element={<PeoplePage />} />
        {isAdmin && <Route path="users" element={<UsersPage />} />}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

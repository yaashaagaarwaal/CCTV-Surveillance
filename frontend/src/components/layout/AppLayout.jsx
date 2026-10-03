import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Activity, Bell, Film, LayoutDashboard, Menu, ScanFace, ShieldCheck, Users, Video, X } from 'lucide-react'
import { api } from '../../api'
import { usePolling } from '../../hooks/usePolling'
import { AlertsProvider } from '../../hooks/AlertsProvider'
import { useAlerts } from '../../hooks/useAlerts'
import { useNow } from '../../hooks/useNow'
import { useAuth } from '../../hooks/useAuth'
import AccountMenu from '../AccountMenu'
import AlertToasts from '../AlertToasts'
import { formatClock } from '../../utils/format'
import { StatusDot } from '../ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/cameras', label: 'Cameras', icon: Video },
  { to: '/alerts', label: 'Alerts', icon: Bell, badge: true },
  { to: '/events', label: 'Events', icon: Activity },
  { to: '/recordings', label: 'Recordings', icon: Film },
  { to: '/people', label: 'People', icon: ScanFace },
  { to: '/users', label: 'Users', icon: Users, adminOnly: true },
]

function SidebarContent({ onNavigate }) {
  const { unread } = useAlerts()
  const { isAdmin } = useAuth()
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-600/20 text-sky-400">
          <ShieldCheck className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <p className="font-semibold tracking-tight">Smart CCTV</p>
          <p className="text-xs text-slate-500">AI Surveillance</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {NAV.filter((item) => !item.adminOnly || isAdmin).map(({ to, label, icon: Icon, end, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive ? 'bg-sky-600/15 text-sky-300' : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-100'
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
            {badge && unread > 0 && (
              <span className="ml-auto rounded-full bg-red-600 px-1.5 text-[11px] font-bold tabular-nums text-white">
                {unread}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <p className="px-5 py-4 text-xs text-slate-600">Motion + YOLO person detection</p>
    </div>
  )
}

function Shell() {
  const { unread } = useAlerts()
  const [menuOpen, setMenuOpen] = useState(false)
  const now = useNow()
  const { data: health, error } = usePolling(api.health, 5000)
  const backendUp = !!health && !error

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 lg:flex">
      <aside className="hidden w-60 shrink-0 border-r border-slate-800 bg-slate-950 lg:block">
        <div className="sticky top-0 h-screen">
          <SidebarContent />
        </div>
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/70" onClick={() => setMenuOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-slate-800 bg-slate-950">
            <button
              onClick={() => setMenuOpen(false)}
              aria-label="Close menu"
              className="absolute right-3 top-4 rounded p-1 text-slate-400 hover:bg-slate-800"
            >
              <X className="h-5 w-5" />
            </button>
            <SidebarContent onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-800 bg-slate-950/90 px-4 py-3 backdrop-blur sm:px-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMenuOpen(true)}
              aria-label="Open menu"
              className="rounded p-1.5 text-slate-300 hover:bg-slate-800 lg:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-2 text-sm">
              <StatusDot status={backendUp ? 'online' : 'offline'} />
              <span className={backendUp ? 'text-slate-300' : 'text-red-400'}>
                {backendUp ? 'System online' : 'Backend unreachable'}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Link
              to="/alerts"
              aria-label={`Alerts (${unread} unread)`}
              className="relative rounded p-1.5 text-slate-300 hover:bg-slate-800"
            >
              <Bell className="h-5 w-5" />
              {unread > 0 && (
                <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-red-600 px-1 text-center text-[10px] font-bold leading-4 text-white">
                  {unread}
                </span>
              )}
            </Link>
            <time className="hidden font-mono text-sm tabular-nums text-slate-400 sm:block">{formatClock(now)}</time>
            <AccountMenu />
          </div>
        </header>

        <main className="min-w-0 flex-1 p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
      <AlertToasts />
    </div>
  )
}

export default function AppLayout() {
  return (
    <AlertsProvider>
      <Shell />
    </AlertsProvider>
  )
}

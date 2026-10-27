import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Activity, Bell, Film, LayoutDashboard, Menu, ScanFace, Users, Video, X } from 'lucide-react'
import { api } from '../../api'
import { usePolling } from '../../hooks/usePolling'
import { AlertsProvider } from '../../hooks/AlertsProvider'
import { useAlerts } from '../../hooks/useAlerts'
import { useNow } from '../../hooks/useNow'
import { useAuth } from '../../hooks/useAuth'
import AccountMenu, { SignOutButton } from '../AccountMenu'
import AlertToasts from '../AlertToasts'
import { formatClock } from '../../utils/format'
import Logo from '../Logo'
import { StatusDot } from '../ui'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
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
      <div className="px-5 py-5">
        <Logo to="/dashboard" onClick={onNavigate} />
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
                isActive ? 'bg-sky-500/10 text-sky-300 ring-1 ring-sky-400/20' : 'text-slate-400 hover:bg-white/[0.05] hover:text-slate-100'
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

      <Link to="/" onClick={onNavigate} className="px-5 py-4 text-xs text-slate-600 transition-colors hover:text-sky-300">
        ← Homepage
      </Link>
    </div>
  )
}

function Shell() {
  const { unread, connection } = useAlerts()
  const [menuOpen, setMenuOpen] = useState(false)
  const now = useNow()
  const { data: health, error } = usePolling(api.health, 5000)
  const backendUp = !!health && !error

  return (
    <div className="min-h-screen bg-ink bg-[radial-gradient(ellipse_60%_40%_at_70%_-10%,rgb(37_99_235/0.14),transparent)] text-slate-100 lg:flex">
      <aside className="hidden w-60 shrink-0 border-r border-white/[0.06] bg-black/30 lg:block">
        <div className="sticky top-0 h-screen">
          <SidebarContent />
        </div>
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/70" onClick={() => setMenuOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-white/[0.06] bg-[#070a10]">
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
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-white/[0.06] bg-[#05070b]/80 px-4 py-3 backdrop-blur-xl sm:px-6">
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
              {backendUp && (
                <span
                  title={connection === 'live' ? 'Alerts are delivered the moment they happen' : 'Reconnecting to the live alert feed; alerts are still checked every few seconds'}
                  className={`ml-1 hidden items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium sm:inline-flex ${
                    connection === 'live' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                  }`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${connection === 'live' ? 'bg-emerald-400' : 'animate-pulse bg-amber-400'}`} />
                  {connection === 'live' ? 'Live alerts' : 'Connecting alerts…'}
                </span>
              )}
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
            <SignOutButton />
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

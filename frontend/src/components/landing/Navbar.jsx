import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { LayoutDashboard, LogIn, Menu, X } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import Logo from '../Logo'

const LINKS = [
  { id: 'top', label: 'Home' },
  { id: 'features', label: 'Features' },
  { id: 'how-it-works', label: 'How It Works' },
  { id: 'about', label: 'About' },
]

// Which section is on screen, so the matching link is highlighted.
function useActiveSection() {
  const [active, setActive] = useState('top')
  useEffect(() => {
    const onScroll = () => {
      const probe = window.scrollY + 140
      let current = 'top'
      for (const { id } of LINKS) {
        const el = document.getElementById(id)
        if (el && el.offsetTop <= probe) current = id
      }
      setActive(current)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  return active
}

export default function Navbar() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const active = useActiveSection()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const cta = signedIn
    ? { to: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard }
    : { to: '/login', label: 'Login', Icon: LogIn }

  return (
    <header className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${scrolled || open ? 'border-b border-white/[0.08] bg-[#05070b]/80 backdrop-blur-xl' : 'border-b border-transparent'}`}>
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8" aria-label="Main">
        <Logo subtitle={null} />

        <ul className="hidden items-center gap-1 md:flex">
          {LINKS.map(({ id, label }) => (
            <li key={id}>
              <a
                href={id === 'top' ? '#top' : `#${id}`}
                className={`rounded-lg px-3.5 py-2 text-sm font-medium transition-colors ${active === id ? 'text-sky-300' : 'text-slate-400 hover:text-slate-100'}`}
              >
                {label}
              </a>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-2">
          <Link
            to={cta.to}
            className="hidden items-center gap-2 rounded-lg border border-sky-400/30 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-200 transition-all hover:border-sky-300/60 hover:bg-sky-500/20 sm:inline-flex"
          >
            <cta.Icon className="h-4 w-4" />
            {cta.label}
          </Link>
          <button
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
            className="rounded-lg p-2 text-slate-300 hover:bg-white/10 md:hidden"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </nav>

      {open && (
        <div className="border-t border-white/[0.08] px-4 pb-5 pt-3 md:hidden">
          <ul className="space-y-1">
            {LINKS.map(({ id, label }) => (
              <li key={id}>
                <a href={`#${id}`} onClick={() => setOpen(false)} className={`block rounded-lg px-3 py-2.5 text-sm font-medium ${active === id ? 'bg-sky-500/10 text-sky-300' : 'text-slate-300'}`}>
                  {label}
                </a>
              </li>
            ))}
            <li>
              <Link to={cta.to} className="mt-2 flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-sky-500 to-blue-600 px-3 py-2.5 text-sm font-semibold text-white">
                <cta.Icon className="h-4 w-4" />
                {cta.label}
              </Link>
            </li>
          </ul>
        </div>
      )}
    </header>
  )
}

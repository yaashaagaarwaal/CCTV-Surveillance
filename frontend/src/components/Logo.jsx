import { Link } from 'react-router-dom'

// The shield-and-lens mark used on the landing page, login page and dashboard.
export function LogoMark({ className = 'h-9 w-9' }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#38bdf8" />
          <stop offset="1" stopColor="#2563eb" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="#0b1220" stroke="rgb(56 189 248 / 0.35)" />
      <path d="M16 4.5 6.5 8v7.2c0 5.6 3.9 9.8 9.5 12.3 5.6-2.5 9.5-6.7 9.5-12.3V8z" fill="url(#logo-g)" />
      <circle cx="16" cy="15" r="4.2" fill="#05070b" />
      <circle cx="16" cy="15" r="1.9" fill="#7dd3fc" />
    </svg>
  )
}

export default function Logo({ to = '/', subtitle = 'AI Surveillance', onClick, className = '' }) {
  return (
    <Link to={to} onClick={onClick} className={`group flex items-center gap-3 ${className}`} aria-label="Smart CCTV — home">
      <LogoMark className="h-9 w-9 transition-transform duration-300 group-hover:scale-105" />
      <span className="leading-tight">
        <span className="block font-semibold tracking-tight text-slate-50">Smart CCTV</span>
        {subtitle && <span className="block text-xs text-slate-500">{subtitle}</span>}
      </span>
    </Link>
  )
}

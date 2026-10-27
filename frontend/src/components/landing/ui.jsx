import { Link } from 'react-router-dom'

const BASE = 'inline-flex items-center justify-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold transition-all duration-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400'

// `to` = a route; `href` = an in-page anchor (#features).
function Action({ to, href, className, children, ...rest }) {
  if (to) return <Link to={to} className={`${BASE} ${className}`} {...rest}>{children}</Link>
  return <a href={href} className={`${BASE} ${className}`} {...rest}>{children}</a>
}

export function PrimaryAction(props) {
  return (
    <Action
      {...props}
      className="bg-gradient-to-r from-sky-500 to-blue-600 text-white shadow-[0_8px_30px_-6px_rgba(37,99,235,0.7)] hover:-translate-y-0.5 hover:shadow-[0_12px_40px_-6px_rgba(56,189,248,0.75)]"
    />
  )
}

export function GhostAction(props) {
  return <Action {...props} className="glass text-slate-100 hover:-translate-y-0.5 hover:border-sky-400/40 hover:bg-white/[0.08]" />
}

export function SectionHeading({ eyebrow, title, children }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-400">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-50 sm:text-4xl">{title}</h2>
      {children && <p className="mt-4 text-base leading-relaxed text-slate-400">{children}</p>}
    </div>
  )
}

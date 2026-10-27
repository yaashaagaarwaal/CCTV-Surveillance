import { Card } from './ui'

const TONES = {
  default: 'bg-slate-800 text-slate-300',
  green: 'bg-emerald-500/15 text-emerald-400',
  red: 'bg-red-500/15 text-red-400',
  blue: 'bg-sky-500/15 text-sky-400',
  amber: 'bg-amber-500/15 text-amber-400',
}

export default function StatCard({ icon: Icon, label, value, hint, tone = 'default', loading = false, className = '' }) {
  if (loading) {
    return (
      <Card className={`flex items-center gap-3 p-3 sm:gap-4 sm:p-4 ${className}`} aria-busy="true">
        <div className="hidden h-11 w-11 shrink-0 animate-pulse rounded-lg bg-white/[0.06] sm:block" />
        <div className="min-w-0 flex-1 space-y-2">
          <p className="text-[11px] font-medium uppercase leading-tight tracking-wide text-slate-500 sm:text-xs">{label}</p>
          <div className="h-6 w-14 animate-pulse rounded bg-white/[0.08]" />
          <div className="h-3 w-24 animate-pulse rounded bg-white/[0.05]" />
        </div>
      </Card>
    )
  }
  return (
    <Card className={`flex items-center gap-3 p-3 transition-colors hover:border-white/[0.14] sm:gap-4 sm:p-4 ${className}`}>
      <div className={`hidden h-11 w-11 shrink-0 items-center justify-center rounded-lg sm:flex ${TONES[tone]}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase leading-tight tracking-wide text-slate-500 sm:text-xs">{label}</p>
        <p className="text-2xl font-semibold tabular-nums leading-tight">{value}</p>
        {hint && <p className="text-xs leading-snug text-slate-500">{hint}</p>}
      </div>
    </Card>
  )
}

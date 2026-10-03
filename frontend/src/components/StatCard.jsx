import { Card } from './ui'

const TONES = {
  default: 'bg-slate-800 text-slate-300',
  green: 'bg-emerald-500/15 text-emerald-400',
  red: 'bg-red-500/15 text-red-400',
  blue: 'bg-sky-500/15 text-sky-400',
  amber: 'bg-amber-500/15 text-amber-400',
}

export default function StatCard({ icon: Icon, label, value, hint, tone = 'default' }) {
  return (
    <Card className="flex items-center gap-3 p-3 sm:gap-4 sm:p-4">
      <div className={`hidden h-11 w-11 shrink-0 items-center justify-center rounded-lg sm:flex ${TONES[tone]}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase leading-tight tracking-wide text-slate-500 sm:text-xs">{label}</p>
        <p className="text-2xl font-semibold tabular-nums leading-tight">{value}</p>
        {hint && <p className="truncate text-xs text-slate-500">{hint}</p>}
      </div>
    </Card>
  )
}

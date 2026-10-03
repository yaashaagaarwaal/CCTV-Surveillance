import { useEffect } from 'react'
import { AlertTriangle, Loader2, X } from 'lucide-react'

export const inputClass =
  'w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500 disabled:opacity-50'

const BUTTON_VARIANTS = {
  primary: 'bg-sky-600 text-white hover:bg-sky-500',
  secondary: 'border border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700',
  danger: 'bg-red-600 text-white hover:bg-red-500',
  ghost: 'text-slate-300 hover:bg-slate-800',
}

export function Button({ variant = 'secondary', className = '', ...props }) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_VARIANTS[variant]} ${className}`}
    />
  )
}

export function Card({ className = '', ...props }) {
  return <div {...props} className={`rounded-xl border border-slate-800 bg-slate-900/60 ${className}`} />
}

const BADGE_TONES = {
  slate: 'bg-slate-700/60 text-slate-300',
  green: 'bg-emerald-500/15 text-emerald-400',
  red: 'bg-red-500/15 text-red-400',
  amber: 'bg-amber-500/15 text-amber-400',
  blue: 'bg-sky-500/15 text-sky-400',
  orange: 'bg-orange-500/15 text-orange-400',
}

export function Badge({ tone = 'slate', className = '', ...props }) {
  return (
    <span
      {...props}
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${BADGE_TONES[tone]} ${className}`}
    />
  )
}

const STATUS = {
  online: { label: 'Online', dot: 'bg-emerald-400', tone: 'green', pulse: true },
  connecting: { label: 'Connecting', dot: 'bg-amber-400', tone: 'amber', pulse: true },
  offline: { label: 'Offline', dot: 'bg-red-500', tone: 'red', pulse: false },
  disabled: { label: 'Disabled', dot: 'bg-slate-500', tone: 'slate', pulse: false },
}

export function StatusDot({ status }) {
  const s = STATUS[status] ?? STATUS.offline
  return (
    <span className="relative flex h-2.5 w-2.5">
      {s.pulse && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${s.dot}`} />}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${s.dot}`} />
    </span>
  )
}

export function StatusBadge({ status }) {
  const s = STATUS[status] ?? STATUS.offline
  return (
    <Badge tone={s.tone}>
      <StatusDot status={status} />
      {s.label}
    </Badge>
  )
}

export function Spinner({ className = '' }) {
  return <Loader2 className={`animate-spin text-slate-400 ${className}`} />
}

export function EmptyState({ icon: Icon, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 px-6 py-12 text-center">
      {Icon && <Icon className="mb-3 h-10 w-10 text-slate-600" />}
      <p className="font-medium text-slate-300">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-slate-500">{children}</div>}
    </div>
  )
}

export function ErrorBanner({ children }) {
  if (!children) return null
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  )
}

export function Modal({ title, onClose, children, wide = false }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/75 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className={`w-full rounded-xl border border-slate-800 bg-slate-900 shadow-2xl ${wide ? 'max-w-3xl' : 'max-w-lg'}`}
      >
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export function ConfirmDialog({ title, children, confirmLabel = 'Delete', busy, error, onConfirm, onCancel }) {
  return (
    <Modal title={title} onClose={onCancel}>
      <div className="space-y-4">
        <div className="text-sm text-slate-300">{children}</div>
        <ErrorBanner>{error}</ErrorBanner>
        <div className="flex justify-end gap-2">
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={busy}>
            {busy && <Spinner className="h-4 w-4 text-white" />}
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

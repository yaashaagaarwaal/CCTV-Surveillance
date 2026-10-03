import { useEffect, useRef, useState } from 'react'
import { KeyRound, LogOut, UserCircle } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../hooks/useAuth'
import { Badge, Button, ErrorBanner, Modal, Spinner, inputClass } from './ui'

function ChangePasswordModal({ onClose }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (next !== confirm) return setError('The new passwords do not match')
    setBusy(true)
    setError(null)
    try {
      await api.changePassword(current, next)
      setDone(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title="Change password" onClose={onClose}>
      {done ? (
        <div className="space-y-4">
          <p className="text-sm text-emerald-400">Password changed. Your other signed-in devices were signed out.</p>
          <div className="flex justify-end">
            <Button variant="primary" onClick={onClose}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <input className={inputClass} type="password" placeholder="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" autoFocus />
          <input className={inputClass} type="password" placeholder="New password (10+ characters)" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
          <input className={inputClass} type="password" placeholder="Repeat new password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
          <ErrorBanner>{error}</ErrorBanner>
          <div className="flex justify-end gap-2">
            <Button onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={!current || !next || !confirm || busy}>
              {busy && <Spinner className="h-4 w-4 text-white" />}
              Change password
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

export default function AccountMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [changing, setChanging] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const close = (e) => !ref.current?.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Account menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
      >
        <UserCircle className="h-5 w-5" />
        <span className="hidden sm:inline">{user.username}</span>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-40 mt-2 w-56 overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-2xl">
          <div className="border-b border-slate-800 px-4 py-3">
            <p className="truncate text-sm font-medium">{user.username}</p>
            <Badge tone={user.role === 'admin' ? 'blue' : 'slate'}>{user.role}</Badge>
          </div>
          <button
            onClick={() => {
              setOpen(false)
              setChanging(true)
            }}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            <KeyRound className="h-4 w-4" /> Change password
          </button>
          <button onClick={logout} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-800">
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      )}
      {changing && <ChangePasswordModal onClose={() => setChanging(false)} />}
    </div>
  )
}

import { useState } from 'react'
import { KeyRound, Trash2, UserPlus, Users } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorBanner, Modal, Spinner, inputClass } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime } from '../utils/format'

function UserFormModal({ user, onSubmit, onClose }) {
  const editing = !!user
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('viewer')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSubmit(editing ? { password } : { username, password, role })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <Modal title={editing ? `Reset password — ${user.username}` : 'Add user'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {!editing && (
          <input className={inputClass} placeholder="Username (letters, numbers, . _ -)" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" autoFocus />
        )}
        <input className={inputClass} type="password" placeholder="Password (10+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        {!editing && (
          <select className={inputClass} value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role">
            <option value="viewer">Viewer — can watch, and read/resolve alerts</option>
            <option value="admin">Administrator — full control</option>
          </select>
        )}
        <ErrorBanner>{error}</ErrorBanner>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={(!editing && !username.trim()) || !password || busy}>
            {busy && <Spinner className="h-4 w-4 text-white" />}
            {editing ? 'Set password' : 'Add user'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export default function UsersPage() {
  const { user: me } = useAuth()
  const { data, error, loading, refresh } = usePolling(api.users, 10000)
  const [form, setForm] = useState(null) // 'new' | user (password reset)
  const [deleting, setDeleting] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [deleteBusy, setDeleteBusy] = useState(false)

  const update = async (user, body) => {
    setActionError(null)
    try {
      await api.updateUser(user.id, body)
    } catch (err) {
      setActionError(err.message)
    } finally {
      refresh()
    }
  }

  const confirmDelete = async () => {
    setDeleteBusy(true)
    setActionError(null)
    try {
      await api.deleteUser(deleting.id)
      setDeleting(null)
    } catch (err) {
      setActionError(err.message)
      setDeleting(null)
    } finally {
      setDeleteBusy(false)
      refresh()
    }
  }

  const users = data ?? []
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Users</h1>
          <p className="text-sm text-slate-500">Who can sign in. Viewers can watch and handle alerts but can't change anything else.</p>
        </div>
        <Button variant="primary" onClick={() => setForm('new')}>
          <UserPlus className="h-4 w-4" /> Add user
        </Button>
      </div>

      <ErrorBanner>{error || actionError}</ErrorBanner>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-8 w-8" />
        </div>
      ) : users.length === 0 ? (
        <EmptyState icon={Users} title="No users" />
      ) : (
        <Card className="divide-y divide-slate-800">
          {users.map((u) => (
            <div key={u.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="min-w-0">
                <p className="flex items-center gap-2 font-medium">
                  {u.username}
                  {u.id === me.id && <Badge tone="blue">you</Badge>}
                  {u.disabled && <Badge tone="red">Disabled</Badge>}
                </p>
                <p className="text-xs text-slate-500">{u.last_login_at ? `Last sign-in ${formatDateTime(u.last_login_at)}` : 'Never signed in'}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm"
                  value={u.role}
                  onChange={(e) => update(u, { role: e.target.value })}
                  aria-label={`Role for ${u.username}`}
                >
                  <option value="viewer">Viewer</option>
                  <option value="admin">Administrator</option>
                </select>
                <Button onClick={() => update(u, { disabled: !u.disabled })} disabled={u.id === me.id}>
                  {u.disabled ? 'Enable' : 'Disable'}
                </Button>
                <Button onClick={() => setForm(u)}>
                  <KeyRound className="h-4 w-4" /> Reset password
                </Button>
                <Button variant="ghost" className="text-slate-400 hover:text-red-400" onClick={() => setDeleting(u)} disabled={u.id === me.id} aria-label={`Delete ${u.username}`}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </Card>
      )}

      {form && (
        <UserFormModal
          user={form === 'new' ? null : form}
          onClose={() => setForm(null)}
          onSubmit={async (body) => {
            if (form === 'new') await api.createUser(body)
            else await api.updateUser(form.id, body)
            setForm(null)
            refresh()
          }}
        />
      )}
      {deleting && (
        <ConfirmDialog title="Delete user" confirmLabel="Delete user" busy={deleteBusy} onConfirm={confirmDelete} onCancel={() => setDeleting(null)}>
          Delete <strong>{deleting.username}</strong>? They will be signed out immediately.
        </ConfirmDialog>
      )}
    </div>
  )
}

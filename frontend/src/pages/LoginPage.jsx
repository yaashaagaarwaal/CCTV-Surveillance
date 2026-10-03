import { useState } from 'react'
import { Lock, ShieldCheck } from 'lucide-react'
import { Button, ErrorBanner, Spinner, inputClass } from '../components/ui'
import { useAuth } from '../hooks/useAuth'

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
    } catch (err) {
      setError(err.message)
      setPassword('')
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4 text-slate-100">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-sky-600/20 text-sky-400">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-tight">Smart CCTV</h1>
            <p className="text-xs text-slate-500">Sign in to continue</p>
          </div>
        </div>

        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-300">Username</span>
          <input
            className={inputClass}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-300">Password</span>
          <input
            className={inputClass}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>

        <ErrorBanner>{error}</ErrorBanner>

        <Button variant="primary" type="submit" className="w-full" disabled={!username.trim() || !password || busy}>
          {busy ? <Spinner className="h-4 w-4 text-white" /> : <Lock className="h-4 w-4" />}
          Sign in
        </Button>
        <p className="text-center text-xs text-slate-600">Cameras and recordings are only visible after signing in.</p>
      </form>
    </div>
  )
}

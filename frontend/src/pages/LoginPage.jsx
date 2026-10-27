import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { ArrowLeft, Eye, EyeOff, Lock, LogIn, Moon, ScanEye, ShieldCheck } from 'lucide-react'
import FullScreenSpinner from '../components/FullScreenSpinner'
import Logo from '../components/Logo'
import { Spinner } from '../components/ui'
import { useAuth } from '../hooks/useAuth'

// Where to go after signing in: the page the visitor originally asked for, if it's inside the app.
function destination(location) {
  const path = location.state?.from?.pathname
  return path && path !== '/' && path !== '/login' ? `${path}${location.state.from.search ?? ''}` : '/dashboard'
}

const HIGHLIGHTS = [
  { icon: ScanEye, title: 'AI person detection', text: 'YOLOv8 on every camera' },
  { icon: Moon, title: 'Night surveillance', text: 'Low-light and infrared aware' },
  { icon: ShieldCheck, title: 'Secure local monitoring', text: 'Your video never leaves your computer' },
]

function Field({ id, label, error, children }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-slate-300">
        {label}
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} className="mt-1.5 text-xs text-red-400">
          {error}
        </p>
      )}
    </div>
  )
}

const FIELD =
  'w-full rounded-xl border bg-black/40 px-3.5 py-3 text-sm text-slate-100 placeholder:text-slate-600 transition focus:outline-none focus:ring-2 disabled:opacity-60'
const fieldTone = (invalid) => (invalid ? 'border-red-500/60 focus:border-red-400 focus:ring-red-500/30' : 'border-white/10 focus:border-sky-400 focus:ring-sky-500/30')

export default function LoginPage() {
  const { status, login } = useAuth()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  if (status === 'loading') return <FullScreenSpinner />
  if (status === 'authenticated') return <Navigate to={destination(location)} replace />

  const problems = {
    username: username.trim() ? null : 'Enter your username.',
    password: password ? null : 'Enter your password.',
  }
  const showProblem = (name) => (submitted ? problems[name] : null)

  const submit = async (e) => {
    e.preventDefault()
    setSubmitted(true)
    if (problems.username || problems.password) return
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password) // on success AuthProvider flips to "authenticated" and we redirect above
    } catch (err) {
      setError(err.message)
      setPassword('')
      setSubmitted(false) // show the server's message, not a "password required" prompt for the field we just cleared
      setBusy(false)
    }
  }

  return (
    <div className="relative grid min-h-screen overflow-clip bg-ink text-slate-200 lg:grid-cols-[1.05fr_1fr]">
      {/* ambience */}
      <div className="pointer-events-none absolute inset-0">
        <div className="bg-grid absolute inset-0 animate-drift opacity-60 [mask-image:radial-gradient(ellipse_80%_70%_at_30%_40%,black,transparent)]" />
        <div className="absolute -left-40 top-1/4 h-[28rem] w-[28rem] animate-glow rounded-full bg-sky-500/20 blur-[120px]" />
        <div className="absolute -right-32 bottom-0 h-96 w-96 rounded-full bg-blue-700/20 blur-[110px]" />
      </div>

      {/* brand panel */}
      <aside className="relative hidden flex-col justify-between p-12 lg:flex">
        <Logo to="/" />
        <div className="max-w-md">
          <div className="relative mb-10 h-44 w-44">
            {[0, 1, 2].map((i) => (
              <span key={i} className="absolute inset-0 rounded-full border border-sky-400/30" style={{ transform: `scale(${1 - i * 0.28})`, opacity: 1 - i * 0.2 }} />
            ))}
            <span className="absolute inset-0 animate-spin rounded-full [animation-duration:6s]" style={{ background: 'conic-gradient(from 0deg, rgb(56 189 248 / 0.45), transparent 28%)' }} />
            <span className="absolute left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-300 shadow-[0_0_24px_6px_rgba(56,189,248,0.7)]" />
            <span className="absolute right-6 top-9 h-2 w-2 animate-pulse rounded-full bg-red-400 shadow-[0_0_12px_3px_rgba(248,113,113,0.7)]" />
          </div>
          <h2 className="text-4xl font-semibold leading-tight tracking-tight text-slate-50">
            Your cameras,
            <br />
            <span className="text-gradient">always watching.</span>
          </h2>
          <ul className="mt-8 space-y-3">
            {HIGHLIGHTS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="glass flex items-center gap-3.5 rounded-xl px-4 py-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/15 text-sky-300">
                  <Icon className="h-5 w-5" />
                </span>
                <span className="leading-tight">
                  <span className="block text-sm font-semibold text-slate-100">{title}</span>
                  <span className="text-xs text-slate-500">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-slate-600">Smart AI-Based Home CCTV Surveillance System</p>
      </aside>

      {/* form */}
      <main className="relative flex items-center justify-center p-5 sm:p-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center justify-between lg:hidden">
            <Logo to="/" subtitle={null} />
          </div>

          <form onSubmit={submit} noValidate className="glass space-y-5 rounded-2xl p-7 shadow-[0_30px_100px_-30px_rgba(37,99,235,0.5)] sm:p-9">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-50">Welcome back</h1>
              <p className="mt-1 text-sm text-slate-500">Sign in to your surveillance dashboard.</p>
            </div>

            {error && (
              <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-3.5 py-2.5 text-sm text-red-300">
                {error}
              </div>
            )}

            <Field id="username" label="Username" error={showProblem('username')}>
              <input
                id="username"
                className={`${FIELD} ${fieldTone(showProblem('username'))}`}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                autoFocus
                disabled={busy}
                aria-invalid={Boolean(showProblem('username'))}
                aria-describedby={showProblem('username') ? 'username-error' : undefined}
              />
            </Field>

            <Field id="password" label="Password" error={showProblem('password')}>
              <div className="relative">
                <input
                  id="password"
                  className={`${FIELD} pr-11 ${fieldTone(showProblem('password'))}`}
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Your password"
                  autoComplete="current-password"
                  disabled={busy}
                  aria-invalid={Boolean(showProblem('password'))}
                  aria-describedby={showProblem('password') ? 'password-error' : undefined}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-500 hover:bg-white/10 hover:text-slate-200"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </Field>

            <button
              type="submit"
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-[0_8px_30px_-6px_rgba(37,99,235,0.7)] transition-all hover:shadow-[0_12px_40px_-6px_rgba(56,189,248,0.75)] disabled:cursor-not-allowed disabled:opacity-70"
            >
              {busy ? <Spinner className="h-4 w-4 text-white" /> : <LogIn className="h-4 w-4" />}
              {busy ? 'Signing in…' : 'Sign in'}
            </button>

            <p className="flex items-start gap-2 text-xs leading-relaxed text-slate-500">
              <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Your session lasts until you sign out or close the browser. Repeated wrong passwords temporarily lock the account.
            </p>
          </form>

          <Link to="/" className="mt-6 inline-flex items-center gap-2 text-sm text-slate-500 transition-colors hover:text-sky-300">
            <ArrowLeft className="h-4 w-4" />
            Back to homepage
          </Link>
        </div>
      </main>
    </div>
  )
}

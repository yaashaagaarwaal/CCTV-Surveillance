import { Link } from 'react-router-dom'
import { SearchX } from 'lucide-react'
import Logo from '../components/Logo'
import { useAuth } from '../hooks/useAuth'

export default function NotFoundPage() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-ink px-4 text-center">
      <Logo subtitle={null} />
      <SearchX className="h-12 w-12 text-slate-600" />
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Page not found</h1>
        <p className="mt-1 text-sm text-slate-500">That address doesn’t exist.</p>
      </div>
      <Link to={signedIn ? '/dashboard' : '/'} className="rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 px-5 py-2.5 text-sm font-semibold text-white">
        {signedIn ? 'Back to the dashboard' : 'Back to the homepage'}
      </Link>
    </div>
  )
}

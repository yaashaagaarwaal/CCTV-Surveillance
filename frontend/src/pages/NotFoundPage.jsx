import { Link } from 'react-router-dom'
import { EmptyState } from '../components/ui'
import { SearchX } from 'lucide-react'

export default function NotFoundPage() {
  return (
    <EmptyState icon={SearchX} title="Page not found">
      <Link to="/" className="text-sky-400 hover:underline">
        Back to the dashboard
      </Link>
    </EmptyState>
  )
}

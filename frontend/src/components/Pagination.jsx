import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from './ui'

export default function Pagination({ page, pageSize, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total <= pageSize && page === 0) return null
  const first = total === 0 ? 0 : page * pageSize + 1
  const last = Math.min(total, (page + 1) * pageSize)
  return (
    <div className="flex items-center justify-between pt-4 text-sm text-slate-400">
      <span>
        {first}–{last} of {total}
      </span>
      <div className="flex items-center gap-2">
        <Button onClick={() => onChange(page - 1)} disabled={page === 0} aria-label="Previous page">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="tabular-nums">
          {page + 1} / {pages}
        </span>
        <Button onClick={() => onChange(page + 1)} disabled={page >= pages - 1} aria-label="Next page">
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

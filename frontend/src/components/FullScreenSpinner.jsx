import { Spinner } from './ui'

export default function FullScreenSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink" role="status" aria-label="Loading">
      <Spinner className="h-8 w-8" />
    </div>
  )
}

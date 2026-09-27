import { useEffect, useState } from 'react'

function App() {
  const [status, setStatus] = useState('checking...')
  const [isOnline, setIsOnline] = useState(false)

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => {
        setStatus(data.status)
        setIsOnline(true)
      })
      .catch(() => {
        setStatus('backend unreachable')
        setIsOnline(false)
      })
  }, [])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <h1 className="text-xl font-semibold tracking-tight">
          Smart AI CCTV Surveillance
        </h1>
      </header>

      <main className="p-6">
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-2 text-sm font-medium text-slate-400">
            Backend status
          </h2>
          <div className="flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                isOnline ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-lg font-medium">{status}</span>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App

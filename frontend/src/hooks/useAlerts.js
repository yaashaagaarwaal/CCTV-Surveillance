import { createContext, useContext } from 'react'

export const AlertsContext = createContext(null)

export function useAlerts() {
  const ctx = useContext(AlertsContext)
  if (!ctx) throw new Error('useAlerts must be used inside <AlertsProvider>')
  return ctx
}

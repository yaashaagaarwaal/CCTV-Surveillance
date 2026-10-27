import { useNavigate } from 'react-router-dom'
import { useAuth } from './useAuth'

// Shows the public homepage, then ends the session on the server (the cookie is
// invalidated there). Navigating first matters: once the session is gone the
// route guard would otherwise send the user to the login page instead.
export function useSignOut() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  return async () => {
    navigate('/', { replace: true })
    await logout()
  }
}

/* oxlint-disable react/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import {
  ApiError,
  UNAUTHORIZED_EVENT,
  authApi,
  primeCsrfToken,
  type User,
} from '../api/client'

interface AuthContextValue {
  ready: boolean
  needsSetup: boolean
  user: User | null
  bootstrapError: string | null
  login: (username: string, password: string) => Promise<User>
  logout: () => Promise<void>
  refreshUser: () => Promise<User | null>
  retryBootstrap: () => Promise<void>
  completeSetup: () => void
  setUser: (user: User | null) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  const [needsSetup, setNeedsSetup] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)

  const bootstrap = useCallback(async () => {
    try {
      const status = await authApi.setupStatus()
      setNeedsSetup(status.needs_setup)
      if (status.needs_setup) {
        setUser(null)
        return
      }

      await primeCsrfToken()
      const currentUser = await authApi.me()
      setUser(currentUser)
    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 403)
      ) {
        setUser(null)
        return
      }
      setBootstrapError(
        error instanceof Error ? error.message : '无法连接后端。',
      )
    } finally {
      setReady(true)
    }
  }, [])

  useEffect(() => {
    // State updates occur after the async bootstrap request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void bootstrap()
  }, [bootstrap])

  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const currentUser = await authApi.login(username, password)
    setUser(currentUser)
    setNeedsSetup(false)
    return currentUser
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      setUser(null)
    }
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      const currentUser = await authApi.me()
      setUser(currentUser)
      return currentUser
    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 403)
      ) {
        setUser(null)
        return null
      }
      throw error
    }
  }, [])

  const retryBootstrap = useCallback(async () => {
    setBootstrapError(null)
    setReady(false)
    await bootstrap()
  }, [bootstrap])

  const completeSetup = useCallback(() => {
    setNeedsSetup(false)
    setUser(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      ready,
      needsSetup,
      user,
      bootstrapError,
      login,
      logout,
      refreshUser,
      retryBootstrap,
      completeSetup,
      setUser,
    }),
    [
      ready,
      needsSetup,
      user,
      bootstrapError,
      login,
      logout,
      refreshUser,
      retryBootstrap,
      completeSetup,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return value
}

import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { API_DISPLAY_ORIGIN } from './api/client'
import { useAuth } from './auth/AuthContext'
import { ChangePasswordPage } from './pages/ChangePasswordPage'
import { DashboardPage } from './pages/DashboardPage'
import { GroupDetailPage } from './pages/GroupDetailPage'
import { GroupsPage } from './pages/GroupsPage'
import { ItemDetailPage } from './pages/ItemDetailPage'
import { ItemsPage } from './pages/ItemsPage'
import { LoginPage } from './pages/LoginPage'
import { MyItemDetailPage } from './pages/MyItemDetailPage'
import { MyItemsPage } from './pages/MyItemsPage'
import { SetupPage } from './pages/SetupPage'
import { UsersPage } from './pages/UsersPage'
import './App.css'

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (user.must_change_password) {
    return <Navigate to="/change-password" replace />
  }
  return <>{children}</>
}

function AdminRoute({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (user.must_change_password) {
    return <Navigate to="/change-password" replace />
  }
  if (user.role !== 'admin') {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

function LoadingScreen() {
  return (
    <div className="boot-screen">
      <div className="boot-mark" aria-hidden="true" />
      <p>正在检查登录状态…</p>
    </div>
  )
}

function ConnectionError({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div className="boot-screen">
      <div className="boot-error-card">
        <p className="eyebrow">连接失败</p>
        <h1>暂时连不上后端</h1>
        <p>{message}</p>
        <p className="muted-text">
          请确认后端窗口仍在运行，然后重试。后端地址：{API_DISPLAY_ORIGIN}。
        </p>
        <button className="primary-button" type="button" onClick={onRetry}>
          重新连接
        </button>
      </div>
    </div>
  )
}

function App() {
  const { ready, needsSetup, user, bootstrapError, retryBootstrap } = useAuth()

  if (!ready) {
    return <LoadingScreen />
  }

  if (bootstrapError) {
    return (
      <ConnectionError
        message={bootstrapError}
        onRetry={() => void retryBootstrap()}
      />
    )
  }

  const homePath = user?.must_change_password ? '/change-password' : '/'

  return (
    <Routes>
      <Route
        path="/setup"
        element={
          needsSetup ? (
            <SetupPage />
          ) : (
            <Navigate to={user ? homePath : '/login'} replace />
          )
        }
      />
      <Route
        path="/login"
        element={
          needsSetup ? (
            <Navigate to="/setup" replace />
          ) : user ? (
            <Navigate to={homePath} replace />
          ) : (
            <LoginPage />
          )
        }
      />
      <Route
        path="/change-password"
        element={
          needsSetup ? (
            <Navigate to="/setup" replace />
          ) : user ? (
            <ChangePasswordPage />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/users"
        element={
          <AdminRoute>
            <UsersPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/groups"
        element={
          <AdminRoute>
            <GroupsPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/groups/:groupId"
        element={
          <AdminRoute>
            <GroupDetailPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/items"
        element={
          <AdminRoute>
            <ItemsPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/items/:itemId"
        element={
          <AdminRoute>
            <ItemDetailPage />
          </AdminRoute>
        }
      />
      <Route
        path="/items"
        element={
          <ProtectedRoute>
            <MyItemsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/items/:itemId"
        element={
          <ProtectedRoute>
            <MyItemDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="*"
        element={<Navigate to={user ? homePath : '/login'} replace />}
      />
    </Routes>
  )
}

export default App

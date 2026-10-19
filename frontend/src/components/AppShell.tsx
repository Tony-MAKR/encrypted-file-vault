import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { BrandMark } from './BrandMark'

interface AppShellProps {
  children: ReactNode
  active?: 'dashboard' | 'users' | 'groups' | 'items' | 'my-items'
}

export function AppShell({ children, active = 'dashboard' }: AppShellProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  if (!user) {
    return null
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link className="app-brand" to="/">
          <BrandMark small />
          <span>
            <strong>加密文件管理系统</strong>
            <small>第 4 阶段 · 加密存储</small>
          </span>
        </Link>

        <nav className="app-nav" aria-label="主导航">
          <Link className={active === 'dashboard' ? 'active' : ''} to="/">
            主页
          </Link>
          {user.role === 'admin' && (
            <>
              <Link
                className={active === 'groups' ? 'active' : ''}
                to="/admin/groups"
              >
                用户组
              </Link>
              <Link
                className={active === 'items' ? 'active' : ''}
                to="/admin/items"
              >
                内容条目
              </Link>
              <Link
                className={active === 'users' ? 'active' : ''}
                to="/admin/users"
              >
                用户管理
              </Link>
            </>
          )}
          {user.role === 'user' && (
            <Link
              className={active === 'my-items' ? 'active' : ''}
              to="/items"
            >
              我的内容
            </Link>
          )}
        </nav>

        <div className="user-area">
          <div className="user-chip">
            <span>{user.display_name}</span>
            <small>{user.role === 'admin' ? '管理员' : '普通用户'}</small>
          </div>
          <button
            className="ghost-button"
            type="button"
            onClick={() => void handleLogout()}
          >
            退出
          </button>
        </div>
      </header>

      <main className="page">{children}</main>

      <footer className="app-footer">
        <span>仅限本机开发环境</span>
        <span>第 4 阶段 / 共 9 个阶段</span>
      </footer>
    </div>
  )
}

import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { AppShell } from '../components/AppShell'

function formatDate(value: string | null): string {
  if (!value) {
    return '尚未登录过'
  }
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function DashboardPage() {
  const { user } = useAuth()

  if (!user) {
    return null
  }

  const roleLabel = user.role === 'admin' ? '管理员' : '普通用户'

  return (
    <AppShell active="dashboard">
      <section className="dashboard-hero">
        <p className="eyebrow">第 2 阶段 · 账号与角色</p>
        <h1>欢迎回来，{user.display_name}</h1>
        <p className="lede">
          账号系统已经就绪。下一次迭代会加入用户组和授权，让不同的人只能看到被允许的内容。
        </p>
        <div className="tag-row">
          <span className="role-badge">{roleLabel}</span>
          <span className="stage-badge">第 2 阶段 / 共 9 个阶段</span>
        </div>
      </section>

      <section className="metric-grid" aria-label="账号信息">
        <article className="metric-card">
          <p className="card-label">登录名</p>
          <p className="metric-value">{user.username}</p>
          <p className="card-note">用户名创建后不可修改</p>
        </article>
        <article className="metric-card">
          <p className="card-label">角色</p>
          <p className="metric-value">{roleLabel}</p>
          <p className="card-note">
            {user.role === 'admin'
              ? '可以管理用户账号和角色'
              : '可以查看被授权的内容'}
          </p>
        </article>
        <article className="metric-card">
          <p className="card-label">上次登录</p>
          <p className="metric-value metric-value-small">
            {formatDate(user.last_login)}
          </p>
          <p className="card-note">如果这不是你本人操作，请立即修改密码</p>
        </article>
      </section>

      <section className="panel notice-panel">
        <h2>这一阶段能做什么</h2>
        <ul>
          <li>管理员可以创建、停用、启用用户，重置临时密码，解锁账号。</li>
          <li>所有用户都可以修改自己的密码，退出后会话立即失效。</li>
          <li>系统会记录登录和账号管理操作；第 7 阶段再加入可查询的审计界面。</li>
        </ul>
        <p>
          文件上传、加密、用户组和内容授权还没有加入。请先不要放真实敏感资料到当前版本。
        </p>
      </section>

      {user.role === 'admin' && (
        <section className="panel admin-callout">
          <div>
            <h2>用户管理</h2>
            <p>创建普通用户或管理员，处理临时密码、停用账号和解锁。</p>
          </div>
          <Link className="primary-link" to="/admin/users">
            打开用户管理
          </Link>
        </section>
      )}
    </AppShell>
  )
}

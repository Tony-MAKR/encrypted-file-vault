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
        <p className="eyebrow">第 3 阶段 · 用户组与授权</p>
        <h1>欢迎回来，{user.display_name}</h1>
        <p className="lede">
          现在可以按用户组或个人授权内容了。系统会在后端检查每一次访问；撤销授权或移出组会立即生效。
        </p>
        <div className="tag-row">
          <span className="role-badge">{roleLabel}</span>
          <span className="stage-badge">第 3 阶段 / 共 9 个阶段</span>
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
              ? '可以管理账号、用户组和内容授权'
              : '只能查看被授权的内容'}
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
          <li>管理员可以创建用户组、添加或移出成员。</li>
          <li>管理员可以创建标题、类型和说明等占位条目，并按组或个人授权。</li>
          <li>普通用户只能看到被授权的条目标题和说明；直接访问未授权地址会显示找不到。</li>
          <li>撤销授权、移出组、停用账号都会在下一次请求立即生效。</li>
        </ul>
        <p>
          真实文件上传、加密、解密和下载还没有加入。本阶段的条目只是权限测试占位，请先不要放真实敏感资料。
        </p>
      </section>

      {user.role === 'admin' && (
        <section className="panel admin-callout">
          <div>
            <h2>用户组与内容条目</h2>
            <p>先建组和成员，再创建占位条目并配置授权。</p>
          </div>
          <div className="callout-actions">
            <Link className="primary-link" to="/admin/groups">
              打开用户组
            </Link>
            <Link className="secondary-button button-link" to="/admin/items">
              打开内容条目
            </Link>
          </div>
        </section>
      )}

      {user.role === 'user' && (
        <section className="panel admin-callout">
          <div>
            <h2>我的内容</h2>
            <p>查看你通过用户组或个人授权获得的内容条目。</p>
          </div>
          <Link className="primary-link" to="/items">
            打开我的内容
          </Link>
        </section>
      )}
    </AppShell>
  )
}

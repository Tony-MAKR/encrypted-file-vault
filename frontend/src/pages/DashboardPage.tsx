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
        <p className="eyebrow">第 4 阶段 · 加密存储</p>
        <h1>欢迎回来，{user.display_name}</h1>
        <p className="lede">
          文件和文字秘密现在会在写入磁盘前加密。被授权的人可以查看或下载；未授权的人拿不到正文。
        </p>
        <div className="tag-row">
          <span className="role-badge">{roleLabel}</span>
          <span className="stage-badge">第 4 阶段 / 共 9 个阶段</span>
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
          <li>管理员可以给文字条目添加网址、账号、密码和秘密备注，保存前加密。</li>
          <li>管理员可以上传文件；文件边接收边加密，磁盘上没有明文和原始文件名。</li>
          <li>被授权用户可以查看文字、显示/复制密码，或下载解密后的文件。</li>
          <li>服务器重启后保险箱会锁定，管理员需要输入主密码重新解锁。</li>
          <li>删除进 30 天回收站，可恢复；到期自动清理。</li>
        </ul>
        <p>
          主密码不是登录密码，丢失后所有加密内容无法恢复。请离线保存主密码；加密备份界面将在第 7 阶段加入。
        </p>
      </section>

      {user.role === 'admin' && (
        <section className="panel admin-callout">
          <div>
            <h2>用户组与内容条目</h2>
            <p>先建组和成员，再创建条目、添加加密内容并配置授权。</p>
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

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  adminApi,
  auditApi,
  vaultApi,
  type AdminDashboard,
  type SystemStatus,
  type UserDashboard,
  type VaultStatus,
} from '../api/client'
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

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '加载失败，请稍后再试。'
}

function formatBytes(value: number): string {
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(0)} MB`
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

export function DashboardPage() {
  const { user } = useAuth()

  const [adminData, setAdminData] = useState<AdminDashboard | null>(null)
  const [userData, setUserData] = useState<UserDashboard | null>(null)
  const [vaultStatus, setVaultStatus] = useState<VaultStatus | null>(null)
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) {
      return
    }
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError('')
      try {
        if (user.role === 'admin') {
          const [dashboard, status, system] = await Promise.all([
            adminApi.dashboard(),
            vaultApi.status(),
            auditApi.systemStatus(),
          ])
          if (!cancelled) {
            setAdminData(dashboard)
            setVaultStatus(status)
            setSystemStatus(system)
          }
        } else {
          const [dashboard, status] = await Promise.all([
            vaultApi.dashboard(),
            vaultApi.status(),
          ])
          if (!cancelled) {
            setUserData(dashboard)
            setVaultStatus(status)
          }
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(messageOf(loadError))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    // State updates occur after the async requests resolve.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
    return () => {
      cancelled = true
    }
  }, [user])

  if (!user) {
    return null
  }

  const roleLabel = user.role === 'admin' ? '管理员' : '普通用户'
  const recentItems =
    user.role === 'admin'
      ? (adminData?.recent_items ?? [])
      : (userData?.recent_items ?? [])

  return (
    <AppShell active="dashboard">
      <section className="dashboard-hero">
        <p className="eyebrow">第 7 阶段 · 审计与备份</p>
        <h1>欢迎回来，{user.display_name}</h1>
        <p className="lede">
          关键操作会写入审计记录；管理员可以创建加密备份并验证完整性。加密仍按第 4 阶段规则运行。
        </p>
        <div className="tag-row">
          <span className="role-badge">{roleLabel}</span>
          <span className="stage-badge">第 7 阶段 / 共 9 个阶段</span>
        </div>
      </section>

      {error && (
        <div className="form-error page-banner" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="empty-state">正在加载主页数据…</p>
      ) : user.role === 'admin' ? (
        <>
          <section className="metric-grid" aria-label="系统概览">
            <article className="metric-card">
              <p className="card-label">活跃条目</p>
              <p className="metric-value">{adminData?.active_items ?? 0}</p>
              <p className="card-note">不含回收站</p>
            </article>
            <article className="metric-card">
              <p className="card-label">已加密条目</p>
              <p className="metric-value">
                {adminData?.encrypted_items ?? 0}
              </p>
              <p className="card-note">已经保存了正文的内容</p>
            </article>
            <article className="metric-card">
              <p className="card-label">回收站</p>
              <p className="metric-value">{adminData?.trash_items ?? 0}</p>
              <p className="card-note">30 天内可恢复</p>
            </article>
            <article className="metric-card">
              <p className="card-label">启用用户</p>
              <p className="metric-value">{adminData?.users ?? 0}</p>
              <p className="card-note">不含停用账号</p>
            </article>
            <article className="metric-card">
              <p className="card-label">用户组</p>
              <p className="metric-value">{adminData?.groups ?? 0}</p>
              <p className="card-note">平铺组</p>
            </article>
            <article className="metric-card">
              <p className="card-label">磁盘剩余</p>
              <p className="metric-value metric-value-small">
                {systemStatus ? formatBytes(systemStatus.disk_free_bytes) : '—'}
              </p>
              <p className="card-note">备份目录所在磁盘</p>
            </article>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>最近更新</h2>
                <p>最近修改的 5 个条目。</p>
              </div>
              <Link className="small-button button-link" to="/admin/items">
                查看全部
              </Link>
            </div>
            {recentItems.length === 0 ? (
              <p className="empty-state">还没有条目，先创建第一条内容。</p>
            ) : (
              <ul className="dashboard-list">
                {recentItems.map((item) => (
                  <li key={item.id}>
                    <div>
                      <Link
                        className="text-link"
                        to={`/admin/items/${item.id}`}
                      >
                        {item.title}
                      </Link>
                      <small>
                        {item.item_type_label}
                        {item.category ? ` · ${item.category}` : ' · 未分类'}
                        {item.has_content ? ' · 已加密' : ' · 未添加内容'}
                      </small>
                    </div>
                    <span className="muted-text">
                      {formatDate(item.updated_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel admin-callout">
            <div>
              <h2>保险箱状态</h2>
              <p>
                {vaultStatus?.initialized
                  ? vaultStatus.unlocked
                    ? '已初始化并解锁。当前可以查看和下载加密内容。'
                    : '已初始化但处于锁定状态；需要管理员输入主密码。'
                  : '还没有设置主密码；第一次添加内容时会提示设置。'}
              </p>
            </div>
            <Link className="primary-link" to="/admin/items">
              去内容条目
            </Link>
          </section>

          <section className="panel notice-panel">
            <h2>备份状态</h2>
            {systemStatus?.backup.reminder_due ? (
              <p>
                已经超过 {systemStatus.backup.reminder_days} 天没有成功备份
                {systemStatus.backup.last_backup_at
                  ? `（最近一次：${formatDate(systemStatus.backup.last_backup_at)}）`
                  : '（还没有备份）'}
                。请尽快创建备份，并把备份文件复制到另一块硬盘。
              </p>
            ) : (
              <p>
                最近一次备份：
                {systemStatus?.backup.last_backup_at
                  ? formatDate(systemStatus.backup.last_backup_at)
                  : '尚未备份'}
                。备份包已加密，备份口令和主密码都需要单独保管。
              </p>
            )}
            <div className="callout-actions">
              <Link
                className="secondary-button button-link"
                to="/admin/backup"
              >
                备份与恢复
              </Link>
              <Link className="secondary-button button-link" to="/admin/audit">
                审计日志
              </Link>
            </div>
          </section>
        </>
      ) : (
        <>
          <section className="metric-grid" aria-label="我的概览">
            <article className="metric-card">
              <p className="card-label">可见内容</p>
              <p className="metric-value">
                {userData?.visible_items ?? 0}
              </p>
              <p className="card-note">不含归档和回收站</p>
            </article>
            <article className="metric-card">
              <p className="card-label">角色</p>
              <p className="metric-value">{roleLabel}</p>
              <p className="card-note">只能查看被授权的内容</p>
            </article>
            <article className="metric-card">
              <p className="card-label">上次登录</p>
              <p className="metric-value metric-value-small">
                {formatDate(user.last_login)}
              </p>
              <p className="card-note">
                如果这不是你本人操作，请立即修改密码
              </p>
            </article>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>最近可查看内容</h2>
                <p>最近更新的 5 条被授权内容。</p>
              </div>
              <Link className="small-button button-link" to="/items">
                查看全部
              </Link>
            </div>
            {recentItems.length === 0 ? (
              <p className="empty-state">
                还没有被授权的内容。如果应该有内容，请联系管理员。
              </p>
            ) : (
              <ul className="dashboard-list">
                {recentItems.map((item) => (
                  <li key={item.id}>
                    <div>
                      <Link className="text-link" to={`/items/${item.id}`}>
                        {item.title}
                      </Link>
                      <small>
                        {item.item_type_label}
                        {item.category ? ` · ${item.category}` : ' · 未分类'}
                        {item.has_content ? ' · 已加密' : ' · 未添加内容'}
                      </small>
                    </div>
                    <span className="muted-text">
                      {formatDate(item.updated_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel admin-callout">
            <div>
              <h2>我的内容</h2>
              <p>
                进入列表后可以按分类、标签和类型筛选，并查看文字或下载文件。
              </p>
            </div>
            <Link className="primary-link" to="/items">
              打开我的内容
            </Link>
          </section>
        </>
      )}
    </AppShell>
  )
}

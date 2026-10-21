import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  backupApi,
  type BackupListResponse,
  type BackupRecord,
} from '../api/client'
import { AppShell } from '../components/AppShell'

const PAGE_SIZE = 20

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后再试。'
}

function formatDate(value: string | null): string {
  if (!value) {
    return '从未备份'
  }
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`
  }
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function countSummary(counts: Record<string, number>): string {
  return `账号 ${counts.users ?? 0} · 用户组 ${counts.groups ?? 0} · 条目 ${counts.items ?? 0} · 加密内容 ${counts.contents ?? 0}`
}

export function BackupPage() {
  const [data, setData] = useState<BackupListResponse | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [passphrase, setPassphrase] = useState('')
  const [confirm, setConfirm] = useState('')
  const [note, setNote] = useState('')
  const [creating, setCreating] = useState(false)

  const [verifyTarget, setVerifyTarget] = useState<BackupRecord | null>(null)
  const [verifyPassphrase, setVerifyPassphrase] = useState('')
  const [verifying, setVerifying] = useState(false)

  const load = async (targetPage = page) => {
    setLoading(true)
    setError('')
    try {
      const response = await backupApi.list(targetPage)
      setData(response)
    } catch (loadError) {
      setError(messageOf(loadError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setLoading(true)
      setError('')
      try {
        const response = await backupApi.list(page)
        if (!cancelled) {
          setData(response)
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
    // State updates occur after the async request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void run()
    return () => {
      cancelled = true
    }
  }, [page])

  const summary = data?.summary
  const totalPages = data
    ? Math.max(1, Math.ceil(data.count / PAGE_SIZE))
    : 1

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (passphrase.length < 12) {
      setError('备份口令至少需要 12 位。')
      return
    }
    if (passphrase !== confirm) {
      setError('两次输入的备份口令不一致。')
      return
    }
    setCreating(true)
    setError('')
    setNotice('')
    try {
      const result = await backupApi.create(passphrase, confirm, note)
      setPassphrase('')
      setConfirm('')
      setNote('')
      setNotice(
        `${result.detail} 文件名：${result.backup?.filename ?? ''}。SHA-256：${result.sha256}`,
      )
      await load(1)
      setPage(1)
    } catch (createError) {
      setError(messageOf(createError))
    } finally {
      setCreating(false)
    }
  }

  const handleVerify = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!verifyTarget) {
      return
    }
    setVerifying(true)
    setError('')
    setNotice('')
    try {
      const result = await backupApi.verify(
        verifyTarget.id,
        verifyPassphrase,
      )
      setVerifyPassphrase('')
      setVerifyTarget(null)
      setNotice(
        `${result.detail} 备份创建于 ${formatDate(result.created_at)}，${countSummary(result.counts)}。`,
      )
      await load()
    } catch (verifyError) {
      setError(messageOf(verifyError))
    } finally {
      setVerifying(false)
    }
  }

  return (
    <AppShell active="backup">
      <section className="page-heading">
        <p className="eyebrow">管理员工具</p>
        <h1>备份与恢复</h1>
        <p className="lede">
          备份包包含数据库快照、密文文件、主密钥文件和清单，使用独立的备份口令整体加密。
          备份口令不会保存；丢失后备份包无法打开。
        </p>
      </section>

      <section className="panel backup-summary">
        <div>
          <h2>最近一次备份</h2>
          <p>
            {summary?.last_backup_at
              ? `${formatDate(summary.last_backup_at)}（${summary.days_since_last_backup ?? 0} 天前）`
              : '还没有创建过备份。'}
          </p>
          {summary?.reminder_due && (
            <p className="warning-text">
              已经超过 {summary.reminder_days} 天没有成功备份，请尽快创建并复制到另一块硬盘。
            </p>
          )}
        </div>
        <span
          className={`status-pill ${summary?.reminder_due ? 'status-pending' : 'status-on'}`}
        >
          {summary?.reminder_due ? '需要备份' : '备份正常'}
        </span>
      </section>

      {error && (
        <div className="form-error page-banner" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="form-success page-banner" role="status">
          {notice}
        </div>
      )}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>创建加密备份</h2>
            <p>
              备份口令至少 12 位，建议用一个和主密码、登录密码都不同的长短语。
            </p>
          </div>
        </div>

        <form className="backup-form" onSubmit={(event) => void handleCreate(event)}>
          <div className="field-grid">
            <div className="field">
              <label htmlFor="backup-passphrase">备份口令</label>
              <input
                id="backup-passphrase"
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                value={passphrase}
                onChange={(event) => setPassphrase(event.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="backup-confirm">确认备份口令</label>
              <input
                id="backup-confirm"
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                required
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="backup-note">说明（可选）</label>
            <input
              id="backup-note"
              type="text"
              maxLength={200}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="例如：每月离线备份"
            />
          </div>
          <p className="field-hint">
            备份口令不会保存在服务器、数据库或 .env 中；系统不会自动删除旧备份。
          </p>
          <div className="callout-actions">
            <button className="primary-button" type="submit" disabled={creating}>
              {creating ? '正在创建备份…' : '创建备份'}
            </button>
          </div>
        </form>
      </section>

      {verifyTarget && (
        <section className="panel verify-panel">
          <div className="panel-heading">
            <div>
              <h2>验证备份</h2>
              <p>{verifyTarget.filename}</p>
            </div>
            <button
              className="small-button"
              type="button"
              onClick={() => {
                setVerifyTarget(null)
                setVerifyPassphrase('')
              }}
            >
              取消
            </button>
          </div>
          <form onSubmit={(event) => void handleVerify(event)}>
            <div className="field">
              <label htmlFor="verify-passphrase">备份口令</label>
              <input
                id="verify-passphrase"
                type="password"
                autoComplete="current-password"
                value={verifyPassphrase}
                onChange={(event) => setVerifyPassphrase(event.target.value)}
                required
                autoFocus
              />
            </div>
            <button className="primary-button" type="submit" disabled={verifying}>
              {verifying ? '正在验证…' : '开始验证'}
            </button>
          </form>
        </section>
      )}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>备份文件</h2>
            <p>文件保存在服务器的 data/backups 目录。请定期复制到另一块硬盘或另一台电脑。</p>
          </div>
          <span className="table-count">
            共 {data?.count ?? 0} 个 · 第 {page} / {totalPages} 页
          </span>
        </div>

        {loading ? (
          <p className="empty-state">正在加载备份记录…</p>
        ) : !data || data.results.length === 0 ? (
          <p className="empty-state">还没有备份。请在上方创建第一个备份。</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>文件</th>
                  <th>创建时间</th>
                  <th>大小</th>
                  <th>状态</th>
                  <th>创建人</th>
                  <th aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {data.results.map((record) => (
                  <tr key={record.id}>
                    <td>
                      <div className="user-cell">
                        <strong>{record.filename}</strong>
                        <span>v{record.app_version || '—'}</span>
                      </div>
                    </td>
                    <td className="date-cell">{formatDate(record.created_at)}</td>
                    <td>{formatBytes(record.size_bytes)}</td>
                    <td>
                      <span
                        className={`status-pill ${
                          record.status === 'verified'
                            ? 'status-on'
                            : record.status === 'failed'
                              ? 'status-locked'
                              : 'status-pending'
                        }`}
                      >
                        {record.status_label}
                      </span>
                    </td>
                    <td>{record.created_by_username || '—'}</td>
                    <td>
                      <button
                        className="small-button"
                        type="button"
                        disabled={!record.file_exists}
                        onClick={() => {
                          setVerifyTarget(record)
                          setVerifyPassphrase('')
                          setError('')
                          setNotice('')
                        }}
                      >
                        {record.file_exists ? '验证' : '文件缺失'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="pagination-row">
          <button
            className="secondary-button"
            type="button"
            disabled={page <= 1 || loading}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            上一页
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={page >= totalPages || loading}
            onClick={() =>
              setPage((current) => Math.min(totalPages, current + 1))
            }
          >
            下一页
          </button>
        </div>
      </section>

      <section className="panel notice-panel">
        <h2>如何恢复</h2>
        <p>
          恢复会覆盖当前数据库、密文和主密钥文件，只能在服务器本机执行，并且必须先关闭服务器。
          恢复脚本会自动把当前数据保存到 pre-restore 目录；失败时会回滚。
        </p>
        <pre className="code-block">
          {`powershell -ExecutionPolicy Bypass -File scripts/restore-backup.ps1 -File "data\\backups\\你的备份.efbak"`}
        </pre>
        <p>
          恢复后保险箱保持锁定，需要用备份中的账号登录并重新输入主密码。备份口令和主密码必须分别保管。
        </p>
      </section>
    </AppShell>
  )
}

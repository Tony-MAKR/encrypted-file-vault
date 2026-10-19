import { useCallback, useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { vaultApi, type VaultStatus } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { FormField } from './FormField'

interface VaultGateProps {
  children: ReactNode
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后再试。'
}

export function VaultGate({ children }: VaultGateProps) {
  const { user } = useAuth()

  const [status, setStatus] = useState<VaultStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [setupPassword, setSetupPassword] = useState('')
  const [setupConfirm, setSetupConfirm] = useState('')
  const [savedAck, setSavedAck] = useState(false)
  const [unlockPassword, setUnlockPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const loadStatus = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setStatus(await vaultApi.status())
    } catch (loadError) {
      setError(messageOf(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // State updates occur after the async status request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadStatus()
  }, [loadStatus])

  const initialize = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setNotice('')
    if (setupPassword !== setupConfirm) {
      setError('两次输入的主密码不一致。')
      return
    }
    if (!savedAck) {
      setError('请先确认你已离线保存主密码。')
      return
    }
    setBusy(true)
    try {
      const next = await vaultApi.initialize(setupPassword, setupConfirm)
      setStatus(next)
      setSetupPassword('')
      setSetupConfirm('')
      setNotice('保险箱已初始化并解锁，可以继续添加加密内容。')
    } catch (initializeError) {
      setError(messageOf(initializeError))
    } finally {
      setBusy(false)
    }
  }

  const unlock = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setNotice('')
    setBusy(true)
    try {
      const next = await vaultApi.unlock(unlockPassword)
      setStatus(next)
      setUnlockPassword('')
      setNotice('保险箱已解锁。')
    } catch (unlockError) {
      setError(messageOf(unlockError))
    } finally {
      setBusy(false)
    }
  }

  const lock = async () => {
    setError('')
    setNotice('')
    setBusy(true)
    try {
      const next = await vaultApi.lock()
      setStatus(next)
      setNotice('保险箱已锁定；需要重新输入主密码才能查看内容。')
    } catch (lockError) {
      setError(messageOf(lockError))
    } finally {
      setBusy(false)
    }
  }

  if (!user) {
    return null
  }

  if (loading) {
    return (
      <section className="panel">
        <p className="empty-state">正在检查保险箱状态…</p>
      </section>
    )
  }

  if (error && !status) {
    return (
      <section className="panel">
        <h2>无法读取保险箱状态</h2>
        <p className="form-error page-banner" role="alert">
          {error}
        </p>
        <button
          className="secondary-button"
          type="button"
          onClick={() => void loadStatus()}
        >
          重试
        </button>
      </section>
    )
  }

  if (!status) {
    return null
  }

  if (status.initialized && status.unlocked) {
    return (
      <div className="vault-unlocked">
        {user.role === 'admin' && (
          <div className="vault-status-row">
            <span>保险箱已解锁</span>
            <button
              className="small-button"
              type="button"
              onClick={() => void lock()}
              disabled={busy}
            >
              {busy ? '正在锁定…' : '锁定保险箱'}
            </button>
          </div>
        )}
        {notice && (
          <div className="form-success page-banner" role="status">
            {notice}
          </div>
        )}
        {children}
      </div>
    )
  }

  if (user.role !== 'admin') {
    return (
      <section className="panel notice-panel">
        <h2>保险箱当前未解锁</h2>
        <p>
          {status.initialized
            ? '管理员需要先输入主密码解锁，之后才能查看或下载加密内容。请联系管理员。'
            : '管理员还没有设置保险箱主密码。请联系管理员完成初始化。'}
        </p>
      </section>
    )
  }

  if (!status.initialized) {
    return (
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>第一次使用加密功能：设置主密码</h2>
            <p>
              主密码不是你的登录密码，只用于解锁服务器上的保险箱。它不会保存在服务器上。
            </p>
          </div>
        </div>

        {error && (
          <div className="form-error page-banner" role="alert">
            {error}
          </div>
        )}

        <div className="vault-warning">
          <strong>请先认真阅读：</strong>
          <p>
            主密码一旦丢失，所有加密内容将永久无法恢复，没有找回或后门。请现在就把它写在纸上放进保险柜，或存入离线密码管理器；不要和数据库备份放在同一块硬盘上。
          </p>
        </div>

        <form
          className="form"
          onSubmit={(event) => void initialize(event)}
        >
          <FormField
            label="主密码（至少 12 位）"
            name="master_password"
            type="password"
            value={setupPassword}
            onChange={(event) => setSetupPassword(event.target.value)}
            minLength={12}
            maxLength={128}
            autoComplete="new-password"
            hint="建议用 4 个不相关的词组成一句长短语。"
            required
          />
          <FormField
            label="确认主密码"
            name="master_password_confirm"
            type="password"
            value={setupConfirm}
            onChange={(event) => setSetupConfirm(event.target.value)}
            minLength={12}
            maxLength={128}
            autoComplete="new-password"
            required
          />
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={savedAck}
              onChange={(event) => setSavedAck(event.target.checked)}
            />
            <span>我已离线保存主密码，并知道丢失后无法恢复。</span>
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={busy || !savedAck}
          >
            {busy ? '正在初始化…' : '设置主密码并解锁'}
          </button>
        </form>
      </section>
    )
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>保险箱已锁定</h2>
          <p>输入主密码后，才能查看或下载加密内容。</p>
        </div>
      </div>

      {error && (
        <div className="form-error page-banner" role="alert">
          {error}
        </div>
      )}

      <form className="form" onSubmit={(event) => void unlock(event)}>
        <FormField
          label="主密码"
          name="unlock_master_password"
          type="password"
          value={unlockPassword}
          onChange={(event) => setUnlockPassword(event.target.value)}
          maxLength={128}
          autoComplete="current-password"
          required
          autoFocus
        />
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? '正在解锁…' : '解锁保险箱'}
        </button>
      </form>
    </section>
  )
}

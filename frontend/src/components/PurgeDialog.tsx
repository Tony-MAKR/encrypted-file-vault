import { useState } from 'react'
import type { FormEvent } from 'react'
import { adminApi } from '../api/client'
import { FormField } from './FormField'

interface PurgeDialogProps {
  item: { id: number; title: string }
  onClose: () => void
  onPurged: () => void
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '永久删除失败，请稍后再试。'
}

export function PurgeDialog({ item, onClose, onPurged }: PurgeDialogProps) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      await adminApi.purgeItem(item.id, password)
      setPassword('')
      onPurged()
    } catch (purgeError) {
      setError(messageOf(purgeError))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) {
          onClose()
        }
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="purge-title"
      >
        <h2 id="purge-title">永久删除“{item.title}”</h2>
        <div className="vault-warning">
          <strong>此操作不可恢复。</strong>
          <p>
            条目、加密正文、授权和密文文件都会被删除。请确认这不是你还需要的内容。
          </p>
        </div>
        <p className="modal-copy">
          为了确认是你本人操作，请重新输入<strong>登录密码</strong>
          （不是保险箱主密码）。
        </p>

        <form className="form" onSubmit={(event) => void submit(event)}>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <FormField
            label="登录密码"
            name="purge_current_password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            maxLength={128}
            autoComplete="current-password"
            required
            autoFocus
          />
          <div className="modal-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={onClose}
              disabled={busy}
            >
              取消
            </button>
            <button
              className="danger-button"
              type="submit"
              disabled={busy || !password}
            >
              {busy ? '正在删除…' : '确认永久删除'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

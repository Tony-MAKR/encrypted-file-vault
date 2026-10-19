import { useEffect, useState } from 'react'
import {
  vaultApi,
  type MyVaultItem,
  type SafeTextContent,
} from '../api/client'

interface UserContentSectionProps {
  item: MyVaultItem
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后再试。'
}

function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function UserContentSection({ item }: UserContentSectionProps) {
  const [textContent, setTextContent] = useState<SafeTextContent | null>(null)
  const [loading, setLoading] = useState(item.item_type === 'text')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revealedPassword, setRevealedPassword] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!item.has_content || item.item_type !== 'text') {
      // Nothing to decrypt for an empty or file item.
      // oxlint-disable-next-line react/set-state-in-effect
      setLoading(false)
      return
    }
    let cancelled = false
    vaultApi
      .getTextContent(item.id)
      .then((data) => {
        if (!cancelled) {
          setTextContent(data)
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(messageOf(loadError))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [item.id, item.has_content, item.item_type])

  const reveal = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const data = await vaultApi.revealPassword(item.id)
      setRevealedPassword(data.password)
    } catch (revealError) {
      setError(messageOf(revealError))
    } finally {
      setBusy(false)
    }
  }

  const copyPassword = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      let password = revealedPassword
      if (!password) {
        const data = await vaultApi.revealPassword(item.id)
        password = data.password
        setRevealedPassword(password)
      }
      await navigator.clipboard.writeText(password)
      await vaultApi.auditCopy(item.id)
      setNotice('密码已复制到剪贴板。请注意不要在公共电脑上保留。')
    } catch (copyError) {
      setError(
        copyError instanceof Error
          ? copyError.message
          : '复制失败，请手动选择密码。',
      )
    } finally {
      setBusy(false)
    }
  }

  const downloadFile = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const file = await vaultApi.downloadFile(item.id)
      const url = URL.createObjectURL(file.blob)
      const link = document.createElement('a')
      link.href = url
      link.download = file.filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      setNotice('文件已开始下载。下载后文件将离开系统保护，无法远程撤回。')
    } catch (downloadError) {
      setError(messageOf(downloadError))
    } finally {
      setBusy(false)
    }
  }

  if (!item.has_content) {
    return (
      <section className="panel notice-panel">
        <h2>还没有加密正文</h2>
        <p>管理员还没有为这条条目添加文字或文件内容。</p>
      </section>
    )
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>
            {item.item_type === 'text' ? '加密文字内容' : '加密文件内容'}
          </h2>
          <p>
            内容已加密保存
            {item.content_size > 0
              ? ` · ${formatSize(item.content_size)}`
              : ''}
            。只有被授权的人能看到明文。
          </p>
        </div>
      </div>

      {notice && (
        <div className="form-success page-banner" role="status">
          {notice}
        </div>
      )}
      {error && (
        <div className="form-error page-banner" role="alert">
          {error}
        </div>
      )}

      {item.item_type === 'text' ? (
        loading ? (
          <p className="empty-state">正在解密内容…</p>
        ) : textContent ? (
          <>
            <dl className="info-list">
              <div>
                <dt>网址 / 地址</dt>
                <dd className="secret-value">
                  {textContent.url || '—'}
                </dd>
              </div>
              <div>
                <dt>账号</dt>
                <dd className="secret-value">
                  {textContent.username || '—'}
                </dd>
              </div>
              <div>
                <dt>密码</dt>
                <dd>
                  {textContent.has_password ? (
                    <span className="password-row">
                      <code className="secret-value">
                        {revealedPassword
                          ? revealedPassword
                          : '••••••••••••'}
                      </code>
                      {revealedPassword ? (
                        <button
                          className="small-button"
                          type="button"
                          onClick={() => setRevealedPassword('')}
                        >
                          隐藏
                        </button>
                      ) : (
                        <button
                          className="small-button"
                          type="button"
                          onClick={() => void reveal()}
                          disabled={busy}
                        >
                          显示密码
                        </button>
                      )}
                      <button
                        className="small-button small-button-accent"
                        type="button"
                        onClick={() => void copyPassword()}
                        disabled={busy}
                      >
                        复制密码
                      </button>
                    </span>
                  ) : (
                    <span className="muted-text">未设置密码</span>
                  )}
                </dd>
              </div>
              <div>
                <dt>秘密备注</dt>
                <dd className="secret-value">
                  {textContent.notes || '—'}
                </dd>
              </div>
            </dl>
            <p className="field-hint">
              显示和复制密码会写安全日志。请不要在公共电脑上保持密码可见。
            </p>
          </>
        ) : (
          <p className="empty-state">无法读取文字内容。</p>
        )
      ) : (
        <div className="file-download-box">
          <p>
            文件已加密保存，原始文件名和内容只有授权用户下载时才会解密。
          </p>
          <p className="field-hint">
            下载后文件将离开系统保护，无法远程撤回；请确认接收者有权查看。
          </p>
          <button
            className="primary-button"
            type="button"
            onClick={() => void downloadFile()}
            disabled={busy}
          >
            {busy ? '正在准备下载…' : '下载并解密文件'}
          </button>
        </div>
      )}
    </section>
  )
}

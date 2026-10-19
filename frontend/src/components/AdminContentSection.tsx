import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import {
  adminApi,
  vaultApi,
  type SafeTextContent,
  type TextContentPayload,
  type VaultItemDetail,
} from '../api/client'
import { FormField } from './FormField'
import { TextareaField } from './TextareaField'

interface AdminContentSectionProps {
  item: VaultItemDetail
  onChanged: () => Promise<void>
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

const EMPTY_TEXT = {
  url: '',
  username: '',
  password: '',
  notes: '',
}

export function AdminContentSection({
  item,
  onChanged,
}: AdminContentSectionProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [textContent, setTextContent] = useState<SafeTextContent | null>(null)
  const [loadingText, setLoadingText] = useState(false)
  const [form, setForm] = useState(EMPTY_TEXT)
  const [clearPassword, setClearPassword] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!item.has_content || item.item_type !== 'text') {
      // Reset the editor when the item has no text content.
      // oxlint-disable-next-line react/set-state-in-effect
      setTextContent(null)
      setForm(EMPTY_TEXT)
      return
    }
    if (!item.can_open_content) {
      return
    }
    let cancelled = false
    setLoadingText(true)
    vaultApi
      .getTextContent(item.id)
      .then((data) => {
        if (cancelled) {
          return
        }
        setTextContent(data)
        setForm({
          url: data.url,
          username: data.username,
          password: '',
          notes: data.notes,
        })
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(messageOf(loadError))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingText(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [
    item.id,
    item.has_content,
    item.item_type,
    item.can_open_content,
    item.updated_at,
  ])

  const updateField = (field: keyof typeof EMPTY_TEXT) =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setForm((current) => ({
        ...current,
        [field]: event.target.value,
      }))
    }

  const saveText = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setNotice('')
    setSaving(true)
    try {
      const payload: TextContentPayload = {
        url: form.url,
        username: form.username,
        notes: form.notes,
        clear_password: clearPassword,
      }
      if (form.password) {
        payload.password = form.password
      } else if (!item.has_content) {
        payload.password = ''
      }
      await adminApi.saveTextContent(item.id, payload)
      setForm((current) => ({ ...current, password: '' }))
      setClearPassword(false)
      setNotice('文字内容已加密保存。')
      await onChanged()
    } catch (saveError) {
      setError(messageOf(saveError))
    } finally {
      setSaving(false)
    }
  }

  const uploadFile = async () => {
    if (!selectedFile) {
      setError('请先选择要上传的文件。')
      return
    }
    setError('')
    setNotice('')
    setUploading(true)
    try {
      await adminApi.uploadFileContent(item.id, selectedFile)
      setSelectedFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      setNotice('文件已加密保存。')
      await onChanged()
    } catch (uploadError) {
      setError(messageOf(uploadError))
    } finally {
      setUploading(false)
    }
  }

  if (item.is_deleted) {
    return (
      <section className="panel notice-panel">
        <h2>条目在回收站中</h2>
        <p>恢复条目后才能编辑或查看内容。</p>
      </section>
    )
  }

  if (item.has_content && !item.can_open_content) {
    return (
      <section className="panel notice-panel">
        <h2>已有加密内容</h2>
        <p>
          这条内容已经加密保存。你目前只有管理权限，没有内容访问授权，因此不能查看或编辑正文。如需查看，请让所有者或管理员给你授权；管理员显式自授权会写日志。
        </p>
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
            {item.has_content
              ? `已加密保存 · ${formatSize(item.content_size)}`
              : '还没有内容。保存时会先加密，再写入磁盘。'}
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
        loadingText ? (
          <p className="empty-state">正在读取加密内容…</p>
        ) : (
          <form
            className="form form-grid"
            onSubmit={(event) => void saveText(event)}
          >
            <FormField
              label="网址 / 地址"
              name="content_url"
              value={form.url}
              onChange={updateField('url')}
              maxLength={1000}
              autoComplete="off"
              placeholder="例如：https://example.com/login"
            />
            <FormField
              label="账号"
              name="content_username"
              value={form.username}
              onChange={updateField('username')}
              maxLength={256}
              autoComplete="off"
              placeholder="登录账号"
            />
            <FormField
              label={textContent?.has_password ? '新密码（留空不修改）' : '密码'}
              name="content_password"
              type="password"
              value={form.password}
              onChange={updateField('password')}
              maxLength={256}
              autoComplete="new-password"
              hint={
                textContent?.has_password
                  ? '留空表示保持原密码；如需更换，请输入新密码。'
                  : '可以留空；密码会随整段文字一起加密。'
              }
            />
            <TextareaField
              label="秘密备注"
              name="content_notes"
              value={form.notes}
              onChange={updateField('notes')}
              maxLength={5000}
              rows={4}
              placeholder="只给被授权者看的备注"
            />
            {textContent?.has_password && (
              <label className="checkbox-row form-span-all">
                <input
                  type="checkbox"
                  checked={clearPassword}
                  onChange={(event) =>
                    setClearPassword(event.target.checked)
                  }
                />
                <span>清空现有密码</span>
              </label>
            )}
            <div className="form-actions form-span-all">
              <button
                className="primary-button"
                type="submit"
                disabled={saving}
              >
                {saving
                  ? '正在加密保存…'
                  : item.has_content
                    ? '保存并重新加密'
                    : '加密保存'}
              </button>
            </div>
          </form>
        )
      ) : (
        <div className="form">
          <div className="field">
            <label htmlFor="vault_file">
              {item.has_content ? '选择新文件替换' : '选择文件'}
            </label>
            <input
              ref={fileInputRef}
              id="vault_file"
              type="file"
              onChange={(event) =>
                setSelectedFile(event.target.files?.[0] ?? null)
              }
              disabled={uploading}
            />
            <p className="field-hint">
              默认上限 200 MB。文件内容会边接收边加密，服务器不会保存明文临时文件。
            </p>
          </div>
          {selectedFile && (
            <p className="muted-text">
              已选择：{selectedFile.name}（{formatSize(selectedFile.size)}）
            </p>
          )}
          <div className="form-actions">
            <button
              className="primary-button"
              type="button"
              onClick={() => void uploadFile()}
              disabled={uploading || !selectedFile}
            >
              {uploading
                ? '正在加密上传…'
                : item.has_content
                  ? '加密并替换文件'
                  : '加密上传'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

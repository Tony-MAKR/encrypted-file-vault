import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { AuthShell } from '../components/AuthShell'
import { FormField } from '../components/FormField'

interface PasswordForm {
  current_password: string
  new_password: string
  new_password_confirm: string
}

const EMPTY_FORM: PasswordForm = {
  current_password: '',
  new_password: '',
  new_password_confirm: '',
}

export function ChangePasswordPage() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState<PasswordForm>(EMPTY_FORM)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!user) {
    return null
  }

  const forced = user.must_change_password

  const update =
    (field: keyof PasswordForm) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      setForm((current) => ({ ...current, [field]: event.target.value }))
    }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')

    if (form.new_password !== form.new_password_confirm) {
      setError('两次输入的新密码不一致。')
      return
    }

    setSubmitting(true)
    try {
      await authApi.changePassword(form)
      setUser({ ...user, must_change_password: false })
      navigate('/', { replace: true })
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : '修改失败，请稍后再试。',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      eyebrow={forced ? '需要先修改密码' : '账号安全'}
      title={forced ? '设置你的新密码' : '修改密码'}
      subtitle={
        forced
          ? '管理员为你设置了临时密码。请先修改为自己的密码，再继续使用系统。'
          : '修改成功后，其他设备上的登录会话会自动失效。'
      }
      footer={
        forced ? (
          <p>修改完成后会自动进入系统。</p>
        ) : (
          <p>
            <Link className="text-link" to="/">
              返回主页
            </Link>
          </p>
        )
      }
    >
      <form className="form" onSubmit={(event) => void handleSubmit(event)}>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}

        <FormField
          label="当前密码"
          name="current_password"
          type="password"
          value={form.current_password}
          onChange={update('current_password')}
          autoComplete="current-password"
          maxLength={128}
          required
          autoFocus
        />

        <FormField
          label="新密码"
          name="new_password"
          type="password"
          value={form.new_password}
          onChange={update('new_password')}
          autoComplete="new-password"
          minLength={12}
          maxLength={128}
          hint="至少 12 位。可以使用长密码短语，不需要强行加入符号。"
          required
        />

        <FormField
          label="确认新密码"
          name="new_password_confirm"
          type="password"
          value={form.new_password_confirm}
          onChange={update('new_password_confirm')}
          autoComplete="new-password"
          minLength={12}
          maxLength={128}
          required
        />

        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? '正在保存…' : '保存新密码'}
        </button>
      </form>
    </AuthShell>
  )
}

import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { AuthShell } from '../components/AuthShell'
import { FormField } from '../components/FormField'

interface SetupForm {
  username: string
  display_name: string
  password: string
  password_confirm: string
}

const EMPTY_FORM: SetupForm = {
  username: '',
  display_name: '',
  password: '',
  password_confirm: '',
}

export function SetupPage() {
  const { completeSetup } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState<SetupForm>(EMPTY_FORM)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const update =
    (field: keyof SetupForm) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      setForm((current) => ({ ...current, [field]: event.target.value }))
    }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')

    if (form.password !== form.password_confirm) {
      setError('两次输入的密码不一致。')
      return
    }

    setSubmitting(true)
    try {
      await authApi.setup(form)
      completeSetup()
      navigate('/login', { replace: true })
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : '创建失败，请稍后再试。',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      eyebrow="首次使用"
      title="创建第一位管理员"
      subtitle="这个账号会拥有管理其他用户的权限。请使用一个你能妥善保管的强密码。"
      footer={
        <p>
          首次设置只能在这台电脑上完成；设置成功后，入口会自动关闭。
        </p>
      }
    >
      <form className="form" onSubmit={(event) => void handleSubmit(event)}>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}

        <FormField
          label="登录用户名"
          name="username"
          value={form.username}
          onChange={update('username')}
          autoComplete="username"
          placeholder="例如：admin"
          minLength={3}
          maxLength={32}
          pattern="[a-zA-Z0-9_-]{3,32}"
          hint="3–32 位，只能使用字母、数字、下划线和连字符；不区分大小写。"
          required
          autoFocus
        />

        <FormField
          label="显示名"
          name="display_name"
          value={form.display_name}
          onChange={update('display_name')}
          autoComplete="name"
          placeholder="例如：张三"
          maxLength={50}
          hint="登录后在界面上显示的名字，可以使用中文。"
          required
        />

        <FormField
          label="密码"
          name="password"
          type="password"
          value={form.password}
          onChange={update('password')}
          autoComplete="new-password"
          minLength={12}
          maxLength={128}
          hint="至少 12 位；建议使用一句容易记住的长密码短语。"
          required
        />

        <FormField
          label="确认密码"
          name="password_confirm"
          type="password"
          value={form.password_confirm}
          onChange={update('password_confirm')}
          autoComplete="new-password"
          minLength={12}
          maxLength={128}
          required
        />

        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? '正在创建…' : '创建管理员'}
        </button>
      </form>
    </AuthShell>
  )
}

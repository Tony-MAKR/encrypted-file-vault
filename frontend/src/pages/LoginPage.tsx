import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { AuthShell } from '../components/AuthShell'
import { FormField } from '../components/FormField'

interface LoginLocationState {
  notice?: string
}

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const notice = (location.state as LoginLocationState | null)?.notice

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const user = await login(username, password)
      navigate(user.must_change_password ? '/change-password' : '/', {
        replace: true,
      })
    } catch (loginError) {
      setError(
        loginError instanceof Error
          ? loginError.message
          : '登录失败，请稍后再试。',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      eyebrow="加密文件管理系统"
      title="登录保险箱"
      subtitle="使用管理员为你创建的账号登录。账号权限不同，能看到的内容也不同。"
      footer={<p>忘记密码请联系管理员重置；系统暂不提供邮件找回。</p>}
    >
      <form className="form" onSubmit={(event) => void handleSubmit(event)}>
        {notice && (
          <div className="form-success" role="status">
            {notice}
          </div>
        )}
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}

        <FormField
          label="用户名"
          name="username"
          value={username}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            setUsername(event.target.value)
          }
          autoComplete="username"
          maxLength={32}
          required
          autoFocus
        />

        <FormField
          label="密码"
          name="password"
          type="password"
          value={password}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            setPassword(event.target.value)
          }
          autoComplete="current-password"
          maxLength={128}
          required
        />

        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? '正在登录…' : '登录'}
        </button>
      </form>
    </AuthShell>
  )
}

import { useCallback, useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import {
  adminApi,
  type CreateUserPayload,
  type ResetPasswordPayload,
  type User,
  type UserRole,
} from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { AppShell } from '../components/AppShell'
import { FormField } from '../components/FormField'

const PAGE_SIZE = 20

const EMPTY_CREATE_FORM: CreateUserPayload = {
  username: '',
  display_name: '',
  password: '',
  password_confirm: '',
  role: 'user',
}

const EMPTY_RESET_FORM: ResetPasswordPayload = {
  new_password: '',
  new_password_confirm: '',
}

function formatDate(value: string | null): string {
  if (!value) {
    return '从未登录'
  }
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function roleLabel(role: UserRole): string {
  return role === 'admin' ? '管理员' : '普通用户'
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后再试。'
}

export function UsersPage() {
  const { user: currentUser } = useAuth()

  const [users, setUsers] = useState<User[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [notice, setNotice] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] =
    useState<CreateUserPayload>(EMPTY_CREATE_FORM)
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)

  const [resetTarget, setResetTarget] = useState<User | null>(null)
  const [resetForm, setResetForm] =
    useState<ResetPasswordPayload>(EMPTY_RESET_FORM)
  const [resetError, setResetError] = useState('')
  const [resetting, setResetting] = useState(false)

  const loadUsers = useCallback(
    async (targetPage: number, targetQuery: string) => {
      setLoading(true)
      setListError('')
      try {
        const data = await adminApi.listUsers({
          page: targetPage,
          q: targetQuery,
          pageSize: PAGE_SIZE,
        })
        const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE))
        if (targetPage > totalPages) {
          setPage(totalPages)
          return
        }
        setUsers(data.results)
        setTotal(data.count)
      } catch (error) {
        setListError(messageOf(error))
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    // loadUsers updates state after its async request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadUsers(page, query)
  }, [loadUsers, page, query])

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setPage(1)
    setQuery(searchInput.trim())
  }

  const clearSearch = () => {
    setSearchInput('')
    setQuery('')
    setPage(1)
  }

  const updateCreate =
    (field: Exclude<keyof CreateUserPayload, 'role'>) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      setCreateForm((current) => ({
        ...current,
        [field]: event.target.value,
      }))
    }

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setCreateError('')

    if (createForm.password !== createForm.password_confirm) {
      setCreateError('两次输入的密码不一致。')
      return
    }

    setCreating(true)
    try {
      await adminApi.createUser(createForm)
      setNotice(
        `用户 ${createForm.username} 已创建。请把临时密码安全地告诉对方，对方首次登录时必须修改密码。`,
      )
      setCreateForm(EMPTY_CREATE_FORM)
      setShowCreate(false)
      setSearchInput('')
      setQuery('')
      setPage(1)
      await loadUsers(1, '')
    } catch (error) {
      setCreateError(messageOf(error))
    } finally {
      setCreating(false)
    }
  }

  const runAction = async (
    target: User,
    action: () => Promise<unknown>,
    successMessage: string,
  ) => {
    setBusyId(target.id)
    setNotice('')
    setListError('')
    try {
      await action()
      setNotice(successMessage)
      await loadUsers(page, query)
    } catch (error) {
      setListError(messageOf(error))
    } finally {
      setBusyId(null)
    }
  }

  const toggleActive = (target: User) => {
    if (target.is_active) {
      if (
        !window.confirm(
          `确定停用 ${target.display_name} 吗？该用户会立即被踢下线，无法继续登录。`,
        )
      ) {
        return
      }
      void runAction(
        target,
        () => adminApi.disable(target.id),
        `已停用 ${target.display_name}。`,
      )
      return
    }
    void runAction(
      target,
      () => adminApi.enable(target.id),
      `已启用 ${target.display_name}。`,
    )
  }

  const changeRole = (target: User) => {
    const nextRole: UserRole = target.role === 'admin' ? 'user' : 'admin'
    const description =
      nextRole === 'admin'
        ? '该用户将获得管理其他账号的权限。'
        : '该用户将失去管理员权限。'
    if (
      !window.confirm(
        `确定把 ${target.display_name} 的角色改为“${roleLabel(nextRole)}”吗？${description}`,
      )
    ) {
      return
    }
    void runAction(
      target,
      () => adminApi.setRole(target.id, nextRole),
      `已把 ${target.display_name} 设为${roleLabel(nextRole)}。`,
    )
  }

  const unlock = (target: User) => {
    void runAction(
      target,
      () => adminApi.unlock(target.id),
      `已解锁 ${target.display_name}。`,
    )
  }

  const openReset = (target: User) => {
    setResetTarget(target)
    setResetForm(EMPTY_RESET_FORM)
    setResetError('')
  }

  const closeReset = () => {
    if (resetting) {
      return
    }
    setResetTarget(null)
    setResetError('')
  }

  const handleReset = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!resetTarget) {
      return
    }
    setResetError('')
    if (resetForm.new_password !== resetForm.new_password_confirm) {
      setResetError('两次输入的新密码不一致。')
      return
    }

    setResetting(true)
    try {
      await adminApi.resetPassword(resetTarget.id, resetForm)
      setNotice(
        `已为 ${resetTarget.display_name} 设置临时密码。对方下次登录时必须修改密码。`,
      )
      setResetTarget(null)
      setResetForm(EMPTY_RESET_FORM)
      await loadUsers(page, query)
    } catch (error) {
      setResetError(messageOf(error))
    } finally {
      setResetting(false)
    }
  }

  if (!currentUser) {
    return null
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <AppShell active="users">
      <section className="page-heading">
        <div>
          <p className="eyebrow">管理员工具</p>
          <h1>用户管理</h1>
          <p className="lede">
            创建账号、处理临时密码、停用或启用用户。普通用户只能管理自己的密码。
          </p>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={() => {
            setShowCreate((value) => !value)
            setCreateError('')
          }}
        >
          {showCreate ? '收起新建表单' : '新建用户'}
        </button>
      </section>

      {notice && (
        <div className="form-success page-banner" role="status">
          {notice}
        </div>
      )}
      {listError && (
        <div className="form-error page-banner" role="alert">
          {listError}
        </div>
      )}

      {showCreate && (
        <section className="panel create-panel">
          <div className="panel-heading">
            <div>
              <h2>新建用户</h2>
              <p>新用户首次登录时会被要求修改临时密码。</p>
            </div>
          </div>

          <form
            className="form form-grid"
            onSubmit={(event) => void handleCreate(event)}
          >
            {createError && (
              <div className="form-error form-span-all" role="alert">
                {createError}
              </div>
            )}

            <FormField
              label="登录用户名"
              name="new_username"
              value={createForm.username}
              onChange={updateCreate('username')}
              minLength={3}
              maxLength={32}
              placeholder="例如：zhangsan"
              autoComplete="off"
              required
            />
            <FormField
              label="显示名"
              name="new_display_name"
              value={createForm.display_name}
              onChange={updateCreate('display_name')}
              maxLength={50}
              placeholder="例如：张三"
              autoComplete="off"
              required
            />
            <FormField
              label="初始密码"
              name="new_password"
              type="password"
              value={createForm.password}
              onChange={updateCreate('password')}
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              hint="至少 12 位；请通过可信方式告诉用户。"
              required
            />
            <FormField
              label="确认初始密码"
              name="new_password_confirm"
              type="password"
              value={createForm.password_confirm}
              onChange={updateCreate('password_confirm')}
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              required
            />

            <div className="field">
              <label htmlFor="new_role">角色</label>
              <select
                id="new_role"
                value={createForm.role}
                onChange={(event) =>
                  setCreateForm((current) => ({
                    ...current,
                    role: event.target.value as UserRole,
                  }))
                }
              >
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </select>
              <p className="field-hint">建议只给确实需要管理账号的人管理员权限。</p>
            </div>

            <div className="form-actions form-span-all">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setShowCreate(false)}
                disabled={creating}
              >
                取消
              </button>
              <button
                className="primary-button"
                type="submit"
                disabled={creating}
              >
                {creating ? '正在创建…' : '创建用户'}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="panel">
        <div className="table-toolbar">
          <form
            className="search-form"
            onSubmit={(event) => void handleSearch(event)}
          >
            <input
              aria-label="搜索用户"
              placeholder="搜索用户名或显示名"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              maxLength={50}
            />
            <button className="secondary-button" type="submit">
              搜索
            </button>
            {query && (
              <button
                className="ghost-button"
                type="button"
                onClick={clearSearch}
              >
                清除
              </button>
            )}
          </form>
          <span className="table-count">共 {total} 位用户</span>
        </div>

        {loading ? (
          <p className="empty-state">正在加载用户列表…</p>
        ) : users.length === 0 ? (
          <p className="empty-state">没有找到匹配的用户。</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>用户</th>
                  <th>角色</th>
                  <th>状态</th>
                  <th>最后登录</th>
                  <th className="actions-column">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((target) => {
                  const isSelf = target.id === currentUser.id
                  const busy = busyId === target.id
                  return (
                    <tr key={target.id}>
                      <td>
                        <div className="user-cell">
                          <strong>{target.display_name}</strong>
                          <span>@{target.username}</span>
                        </div>
                      </td>
                      <td>
                        <span
                          className={`role-badge ${
                            target.role === 'admin' ? 'role-admin' : ''
                          }`}
                        >
                          {roleLabel(target.role)}
                        </span>
                      </td>
                      <td>
                        <div className="status-stack">
                          {!target.is_active && (
                            <span className="status-pill status-off">
                              已停用
                            </span>
                          )}
                          {target.is_locked && (
                            <span className="status-pill status-locked">
                              已锁定
                            </span>
                          )}
                          {target.must_change_password && (
                            <span className="status-pill status-pending">
                              待改密
                            </span>
                          )}
                          {target.is_active &&
                            !target.is_locked &&
                            !target.must_change_password && (
                              <span className="status-pill status-on">正常</span>
                            )}
                        </div>
                      </td>
                      <td className="date-cell">
                        {formatDate(target.last_login)}
                      </td>
                      <td>
                        {isSelf ? (
                          <span className="muted-text">当前账号</span>
                        ) : (
                          <div className="row-actions">
                            <button
                              className="small-button"
                              type="button"
                              onClick={() => toggleActive(target)}
                              disabled={busy}
                            >
                              {target.is_active ? '停用' : '启用'}
                            </button>
                            <button
                              className="small-button"
                              type="button"
                              onClick={() => changeRole(target)}
                              disabled={busy}
                            >
                              {target.role === 'admin'
                                ? '设为普通用户'
                                : '设为管理员'}
                            </button>
                            <button
                              className="small-button"
                              type="button"
                              onClick={() => openReset(target)}
                              disabled={busy}
                            >
                              重置密码
                            </button>
                            {target.is_locked && (
                              <button
                                className="small-button small-button-accent"
                                type="button"
                                onClick={() => unlock(target)}
                                disabled={busy}
                              >
                                解锁
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="pagination">
          <button
            className="secondary-button"
            type="button"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={page <= 1 || loading}
          >
            上一页
          </button>
          <span>
            第 {page} / {totalPages} 页
          </span>
          <button
            className="secondary-button"
            type="button"
            onClick={() =>
              setPage((value) => Math.min(totalPages, value + 1))
            }
            disabled={page >= totalPages || loading}
          >
            下一页
          </button>
        </div>
      </section>

      {resetTarget && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeReset()
            }
          }}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-password-title"
          >
            <h2 id="reset-password-title">
              为 {resetTarget.display_name} 重置密码
            </h2>
            <p className="modal-copy">
              设置一个临时密码。对方下次登录时必须修改，且旧会话会立即失效。
            </p>
            <form
              className="form"
              onSubmit={(event) => void handleReset(event)}
            >
              {resetError && (
                <div className="form-error" role="alert">
                  {resetError}
                </div>
              )}
              <FormField
                label="临时密码"
                name="reset_password"
                type="password"
                value={resetForm.new_password}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setResetForm((current) => ({
                    ...current,
                    new_password: event.target.value,
                  }))
                }
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                hint="至少 12 位；请通过可信方式告诉对方。"
                required
                autoFocus
              />
              <FormField
                label="确认临时密码"
                name="reset_password_confirm"
                type="password"
                value={resetForm.new_password_confirm}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setResetForm((current) => ({
                    ...current,
                    new_password_confirm: event.target.value,
                  }))
                }
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                required
              />
              <div className="modal-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={closeReset}
                  disabled={resetting}
                >
                  取消
                </button>
                <button
                  className="primary-button"
                  type="submit"
                  disabled={resetting}
                >
                  {resetting ? '正在保存…' : '保存临时密码'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  )
}

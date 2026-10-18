import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  adminApi,
  type GroupPayload,
  type VaultGroupSummary,
} from '../api/client'
import { AppShell } from '../components/AppShell'
import { FormField } from '../components/FormField'
import { TextareaField } from '../components/TextareaField'

const PAGE_SIZE = 20

const EMPTY_FORM: GroupPayload = {
  name: '',
  description: '',
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后再试。'
}

export function GroupsPage() {
  const [groups, setGroups] = useState<VaultGroupSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [notice, setNotice] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<GroupPayload>(EMPTY_FORM)
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)

  const loadGroups = useCallback(
    async (targetPage: number, targetQuery: string) => {
      setLoading(true)
      setListError('')
      try {
        const data = await adminApi.listGroups({
          page: targetPage,
          q: targetQuery,
          pageSize: PAGE_SIZE,
        })
        const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE))
        if (targetPage > totalPages) {
          setPage(totalPages)
          return
        }
        setGroups(data.results)
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
    // loadGroups updates state after its async request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadGroups(page, query)
  }, [loadGroups, page, query])

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setPage(1)
    setQuery(searchInput.trim())
  }

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setCreateError('')
    setCreating(true)
    try {
      await adminApi.createGroup({
        name: form.name.trim(),
        description: form.description.trim(),
      })
      setNotice(`用户组 ${form.name.trim()} 已创建，可以继续添加成员。`)
      setForm(EMPTY_FORM)
      setShowCreate(false)
      setSearchInput('')
      setQuery('')
      setPage(1)
      await loadGroups(1, '')
    } catch (error) {
      setCreateError(messageOf(error))
    } finally {
      setCreating(false)
    }
  }

  const removeGroup = async (group: VaultGroupSummary) => {
    if (group.granted_item_count > 0) {
      setListError(
        `“${group.name}”仍被 ${group.granted_item_count} 条内容授权，请先到条目详情撤销授权，再删除这个组。`,
      )
      return
    }
    if (
      !window.confirm(
        `确定删除用户组“${group.name}”吗？组成员关系会一并清除，此操作不可撤销。`,
      )
    ) {
      return
    }

    setBusyId(group.id)
    setNotice('')
    setListError('')
    try {
      await adminApi.deleteGroup(group.id)
      setNotice(`用户组“${group.name}”已删除。`)
      await loadGroups(page, query)
    } catch (error) {
      setListError(messageOf(error))
    } finally {
      setBusyId(null)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <AppShell active="groups">
      <section className="page-heading">
        <div>
          <p className="eyebrow">管理员工具</p>
          <h1>用户组</h1>
          <p className="lede">
            把用户按职责分组，再按组授权内容。一个用户可以属于多个组；成员变更和撤销授权都会立即生效。
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
          {showCreate ? '收起新建表单' : '新建用户组'}
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
              <h2>新建用户组</h2>
              <p>名称必须唯一；说明可以留空。</p>
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
              label="用户组名称"
              name="group_name"
              value={form.name}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  name: event.target.value,
                }))
              }
              maxLength={50}
              placeholder="例如：财务组"
              autoComplete="off"
              required
            />
            <TextareaField
              label="说明"
              name="group_description"
              value={form.description}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
              maxLength={500}
              rows={3}
              placeholder="这个组负责什么，方便以后管理"
            />
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
                {creating ? '正在创建…' : '创建用户组'}
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
              aria-label="搜索用户组"
              placeholder="搜索组名或说明"
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
                onClick={() => {
                  setSearchInput('')
                  setQuery('')
                  setPage(1)
                }}
              >
                清除
              </button>
            )}
          </form>
          <span className="table-count">共 {total} 个用户组</span>
        </div>

        {loading ? (
          <p className="empty-state">正在加载用户组…</p>
        ) : groups.length === 0 ? (
          <p className="empty-state">
            还没有用户组。先新建一个组，再把用户加进去。
          </p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>用户组</th>
                  <th>说明</th>
                  <th>成员</th>
                  <th>已授权内容</th>
                  <th className="actions-column">操作</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <tr key={group.id}>
                    <td>
                      <Link className="text-link" to={`/admin/groups/${group.id}`}>
                        {group.name}
                      </Link>
                    </td>
                    <td className="truncate-cell">
                      {group.description || <span className="muted-text">—</span>}
                    </td>
                    <td>{group.member_count} 人</td>
                    <td>{group.granted_item_count} 条</td>
                    <td>
                      <div className="row-actions">
                        <Link
                          className="small-button button-link"
                          to={`/admin/groups/${group.id}`}
                        >
                          打开
                        </Link>
                        <button
                          className="small-button"
                          type="button"
                          onClick={() => void removeGroup(group)}
                          disabled={busyId === group.id}
                          title={
                            group.granted_item_count > 0
                              ? `仍被 ${group.granted_item_count} 条内容授权，需先撤销`
                              : '删除这个用户组'
                          }
                        >
                          {group.granted_item_count > 0
                            ? '暂不可删除'
                            : busyId === group.id
                              ? '正在删除…'
                              : '删除'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
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
    </AppShell>
  )
}

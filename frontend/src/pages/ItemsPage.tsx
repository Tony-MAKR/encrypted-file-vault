import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  adminApi,
  type ArchivedFilter,
  type ItemPayload,
  type VaultItemSummary,
  type VaultItemType,
} from '../api/client'
import { AppShell } from '../components/AppShell'
import { FormField } from '../components/FormField'
import { TextareaField } from '../components/TextareaField'

const PAGE_SIZE = 20

type DeletedFilter = 'active' | 'only' | 'all'

const EMPTY_FORM: ItemPayload = {
  title: '',
  item_type: 'text',
  description: '',
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后再试。'
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ItemsPage() {
  const navigate = useNavigate()

  const [items, setItems] = useState<VaultItemSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [itemType, setItemType] = useState('')
  const [archived, setArchived] = useState<ArchivedFilter>('active')
  const [deleted, setDeleted] = useState<DeletedFilter>('active')
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [notice, setNotice] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<ItemPayload>(EMPTY_FORM)
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)

  const loadItems = useCallback(
    async (
      targetPage: number,
      targetQuery: string,
      targetType: string,
      targetArchived: ArchivedFilter,
      targetDeleted: DeletedFilter,
    ) => {
      setLoading(true)
      setListError('')
      try {
        const data = await adminApi.listItems({
          page: targetPage,
          q: targetQuery,
          itemType: targetType,
          archived: targetDeleted === 'active' ? targetArchived : 'all',
          deleted: targetDeleted,
          pageSize: PAGE_SIZE,
        })
        const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE))
        if (targetPage > totalPages) {
          setPage(totalPages)
          return
        }
        setItems(data.results)
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
    // loadItems updates state after its async request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadItems(page, query, itemType, archived, deleted)
  }, [loadItems, page, query, itemType, archived, deleted])

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
      const created = await adminApi.createItem({
        title: form.title.trim(),
        item_type: form.item_type,
        description: form.description.trim(),
      })
      setForm(EMPTY_FORM)
      setShowCreate(false)
      navigate(`/admin/items/${created.id}`)
    } catch (error) {
      setCreateError(messageOf(error))
    } finally {
      setCreating(false)
    }
  }

  const restoreItem = async (item: VaultItemSummary) => {
    if (
      !window.confirm(
        `确定恢复“${item.title}”吗？恢复后，被授权的普通用户会重新看到这条内容。`,
      )
    ) {
      return
    }
    setBusyId(item.id)
    setNotice('')
    setListError('')
    try {
      await adminApi.restoreItem(item.id)
      setNotice(`“${item.title}”已从回收站恢复。`)
      await loadItems(page, query, itemType, archived, deleted)
    } catch (error) {
      setListError(messageOf(error))
    } finally {
      setBusyId(null)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <AppShell active="items">
      <section className="page-heading">
        <div>
          <p className="eyebrow">管理员工具</p>
          <h1>内容条目</h1>
          <p className="lede">
            先创建条目，再在详情页添加加密文字或上传加密文件。标题和说明不加密，正文加密保存。
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
          {showCreate ? '收起新建表单' : '新建条目'}
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
              <h2>新建条目</h2>
              <p>创建者自动成为所有者；类型创建后不能修改。</p>
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
              label="标题"
              name="item_title"
              value={form.title}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  title: event.target.value,
                }))
              }
              maxLength={120}
              placeholder="例如：生产数据库密码"
              autoComplete="off"
              required
            />
            <div className="field">
              <label htmlFor="item_type">类型</label>
              <select
                id="item_type"
                value={form.item_type}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    item_type: event.target.value as VaultItemType,
                  }))
                }
              >
                <option value="text">文字</option>
                <option value="file">文件</option>
              </select>
              <p className="field-hint">文字条目填写网址/账号/密码；文件条目上传文件。</p>
            </div>
            <TextareaField
              label="说明"
              name="item_description"
              value={form.description}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
              maxLength={1000}
              rows={3}
              placeholder="这条内容是做什么的，方便以后识别"
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
                {creating ? '正在创建…' : '创建并设置授权'}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="panel">
        <div className="table-toolbar filter-toolbar">
          <form
            className="search-form"
            onSubmit={(event) => void handleSearch(event)}
          >
            <input
              aria-label="搜索内容条目"
              placeholder="搜索标题或说明"
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
          <div className="filter-controls">
            <select
              aria-label="按类型筛选"
              value={itemType}
              onChange={(event) => {
                setItemType(event.target.value)
                setPage(1)
              }}
            >
              <option value="">全部类型</option>
              <option value="text">文字</option>
              <option value="file">文件</option>
            </select>
            <select
              aria-label="按归档状态筛选"
              value={archived}
              onChange={(event) => {
                setArchived(event.target.value as ArchivedFilter)
                setPage(1)
              }}
              disabled={deleted !== 'active'}
            >
              <option value="active">活跃条目</option>
              <option value="archived">已归档</option>
              <option value="all">全部状态</option>
            </select>
            <select
              aria-label="按回收站状态筛选"
              value={deleted}
              onChange={(event) => {
                const next = event.target.value as DeletedFilter
                setDeleted(next)
                if (next !== 'active') {
                  setArchived('all')
                }
                setPage(1)
              }}
            >
              <option value="active">不含回收站</option>
              <option value="only">只看回收站</option>
              <option value="all">全部（含回收站）</option>
            </select>
            <span className="table-count">共 {total} 条</span>
          </div>
        </div>

        {loading ? (
          <p className="empty-state">正在加载内容条目…</p>
        ) : items.length === 0 ? (
          <p className="empty-state">没有符合条件的内容条目。</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>标题</th>
                  <th>类型</th>
                  <th>所有者</th>
                  <th>授权</th>
                  <th>状态</th>
                  <th>更新时间</th>
                  <th className="actions-column">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link
                        className="text-link"
                        to={`/admin/items/${item.id}`}
                      >
                        {item.title}
                      </Link>
                    </td>
                    <td>
                      <span className="role-badge">{item.item_type_label}</span>
                    </td>
                    <td>{item.owner.display_name}</td>
                    <td>
                      组 {item.group_grant_count} / 人 {item.user_grant_count}
                    </td>
                    <td>
                      <div className="status-stack">
                        {item.is_deleted ? (
                          <span className="status-pill status-off">
                            回收站
                          </span>
                        ) : item.is_archived ? (
                          <span className="status-pill status-off">
                            已归档
                          </span>
                        ) : (
                          <span className="status-pill status-on">活跃</span>
                        )}
                        <span
                          className={`status-pill ${
                            item.has_content ? 'status-on' : 'status-pending'
                          }`}
                        >
                          {item.has_content ? '已加密' : '未添加内容'}
                        </span>
                      </div>
                    </td>
                    <td className="date-cell">{formatDate(item.updated_at)}</td>
                    <td>
                      {item.is_deleted ? (
                        <button
                          className="small-button small-button-accent"
                          type="button"
                          onClick={() => void restoreItem(item)}
                          disabled={busyId === item.id}
                        >
                          {busyId === item.id ? '正在恢复…' : '恢复'}
                        </button>
                      ) : (
                        <Link
                          className="small-button button-link"
                          to={`/admin/items/${item.id}`}
                        >
                          打开内容与授权
                        </Link>
                      )}
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

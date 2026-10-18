import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  vaultApi,
  type MyVaultItem,
} from '../api/client'
import { AppShell } from '../components/AppShell'

const PAGE_SIZE = 20

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '加载失败，请稍后再试。'
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

export function MyItemsPage() {
  const [items, setItems] = useState<MyVaultItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadItems = useCallback(
    async (targetPage: number, targetQuery: string) => {
      setLoading(true)
      setError('')
      try {
        const data = await vaultApi.listMyItems({
          page: targetPage,
          q: targetQuery,
          pageSize: PAGE_SIZE,
        })
        const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE))
        if (targetPage > totalPages) {
          setPage(totalPages)
          return
        }
        setItems(data.results)
        setTotal(data.count)
      } catch (loadError) {
        setError(messageOf(loadError))
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    // loadItems updates state after its async request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadItems(page, query)
  }, [loadItems, page, query])

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setPage(1)
    setQuery(searchInput.trim())
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <AppShell active="my-items">
      <section className="page-heading">
        <div>
          <p className="eyebrow">我的内容</p>
          <h1>被授权的内容</h1>
          <p className="lede">
            这里只显示你通过用户组或个人授权获得访问权的内容。未授权的内容不会出现在列表中。
          </p>
        </div>
      </section>

      <div className="form-success page-banner" role="status">
        本阶段只有标题、类型和说明等元数据；真实文件或加密文字将在第 4 阶段加入。
      </div>

      {error && (
        <div className="form-error page-banner" role="alert">
          {error}
        </div>
      )}

      <section className="panel">
        <div className="table-toolbar">
          <form
            className="search-form"
            onSubmit={(event) => void handleSearch(event)}
          >
            <input
              aria-label="搜索我的内容"
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
          <span className="table-count">共 {total} 条内容</span>
        </div>

        {loading ? (
          <p className="empty-state">正在加载…</p>
        ) : items.length === 0 ? (
          <p className="empty-state">
            目前没有可查看的内容。如果应该有内容，请联系管理员确认授权。
          </p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>标题</th>
                  <th>类型</th>
                  <th>所有者</th>
                  <th>更新时间</th>
                  <th className="actions-column">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link className="text-link" to={`/items/${item.id}`}>
                        {item.title}
                      </Link>
                    </td>
                    <td>
                      <span className="role-badge">{item.item_type_label}</span>
                    </td>
                    <td>{item.owner.display_name}</td>
                    <td className="date-cell">{formatDate(item.updated_at)}</td>
                    <td>
                      <Link
                        className="small-button button-link"
                        to={`/items/${item.id}`}
                      >
                        查看
                      </Link>
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

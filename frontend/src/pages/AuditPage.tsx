import { useEffect, useState } from 'react'
import {
  auditApi,
  type AuditEvent,
  type AuditOptions,
  type Paginated,
} from '../api/client'
import { AppShell } from '../components/AppShell'

const PAGE_SIZE = 50

interface QueryState {
  q: string
  category: string
  action: string
  result: string
  dateFrom: string
  dateTo: string
}

const EMPTY_QUERY: QueryState = {
  q: '',
  category: '',
  action: '',
  result: '',
  dateFrom: '',
  dateTo: '',
}

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
    second: '2-digit',
  })
}

export function AuditPage() {
  const [options, setOptions] = useState<AuditOptions | null>(null)
  const [events, setEvents] = useState<Paginated<AuditEvent> | null>(null)
  const [query, setQuery] = useState<QueryState>(EMPTY_QUERY)
  const [searchInput, setSearchInput] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    auditApi
      .options()
      .then((data) => {
        if (!cancelled) {
          setOptions(data)
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(messageOf(loadError))
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const data = await auditApi.list({ ...query, page })
        if (!cancelled) {
          setEvents(data)
          setExpandedId(null)
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(messageOf(loadError))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    // State updates occur after the async request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
    return () => {
      cancelled = true
    }
  }, [query, page])

  const updateQuery = (patch: Partial<QueryState>) => {
    setQuery((current) => ({ ...current, ...patch }))
    setPage(1)
  }

  const selectedCategory = options?.categories.find(
    (item) => item.value === query.category,
  )
  const actionOptions = selectedCategory
    ? selectedCategory.actions
    : (options?.categories.flatMap((item) => item.actions) ?? [])

  const totalPages = events
    ? Math.max(1, Math.ceil(events.count / PAGE_SIZE))
    : 1

  return (
    <AppShell active="audit">
      <section className="page-heading">
        <p className="eyebrow">管理员工具</p>
        <h1>审计日志</h1>
        <p className="lede">
          查询谁在什么时候做了什么。审计记录只增不改，不包含密码、主密码、密钥或内容明文。
        </p>
      </section>

      <section className="panel">
        <div className="table-toolbar filter-toolbar">
          <form
            className="search-form"
            onSubmit={(event) => {
              event.preventDefault()
              updateQuery({ q: searchInput.trim() })
            }}
          >
            <input
              aria-label="搜索操作人或对象"
              placeholder="搜索操作人或对象"
              value={searchInput}
              maxLength={50}
              onChange={(event) => setSearchInput(event.target.value)}
            />
            <button className="secondary-button" type="submit">
              搜索
            </button>
          </form>
          <span className="table-count">
            共 {events?.count ?? 0} 条 · 第 {page} / {totalPages} 页
          </span>
        </div>

        <div className="filter-controls audit-filters">
          <select
            aria-label="操作类别"
            value={query.category}
            onChange={(event) =>
              updateQuery({ category: event.target.value, action: '' })
            }
          >
            <option value="">全部类别</option>
            {options?.categories.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <select
            aria-label="具体操作"
            value={query.action}
            onChange={(event) => updateQuery({ action: event.target.value })}
          >
            <option value="">全部操作</option>
            {actionOptions.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <select
            aria-label="结果"
            value={query.result}
            onChange={(event) => updateQuery({ result: event.target.value })}
          >
            <option value="">全部结果</option>
            {options?.results.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <label className="inline-date">
            从
            <input
              type="date"
              value={query.dateFrom}
              onChange={(event) =>
                updateQuery({ dateFrom: event.target.value })
              }
            />
          </label>
          <label className="inline-date">
            到
            <input
              type="date"
              value={query.dateTo}
              onChange={(event) => updateQuery({ dateTo: event.target.value })}
            />
          </label>

          <button
            className="small-button"
            type="button"
            onClick={() => {
              setSearchInput('')
              setQuery(EMPTY_QUERY)
              setPage(1)
            }}
          >
            重置
          </button>
        </div>

        {error && (
          <div className="form-error page-banner" role="alert">
            {error}
          </div>
        )}

        {loading ? (
          <p className="empty-state">正在加载审计记录…</p>
        ) : !events || events.results.length === 0 ? (
          <p className="empty-state">没有符合条件的审计记录。</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table audit-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>操作人</th>
                  <th>操作</th>
                  <th>对象</th>
                  <th>结果</th>
                  <th>来源</th>
                  <th aria-label="详情" />
                </tr>
              </thead>
              <tbody>
                {events.results.map((event) => (
                  <FragmentRow
                    key={event.id}
                    event={event}
                    expanded={expandedId === event.id}
                    onToggle={() =>
                      setExpandedId((current) =>
                        current === event.id ? null : event.id,
                      )
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="pagination-row">
          <button
            className="secondary-button"
            type="button"
            disabled={page <= 1 || loading}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            上一页
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={page >= totalPages || loading}
            onClick={() =>
              setPage((current) => Math.min(totalPages, current + 1))
            }
          >
            下一页
          </button>
        </div>
      </section>
    </AppShell>
  )
}

function FragmentRow({
  event,
  expanded,
  onToggle,
}: {
  event: AuditEvent
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr>
        <td className="date-cell">{formatDate(event.created_at)}</td>
        <td>
          <div className="user-cell">
            <strong>{event.actor_username || '系统'}</strong>
            <span>{event.actor_role || '—'}</span>
          </div>
        </td>
        <td>{event.action_label || event.action}</td>
        <td>
          {event.target_label || '—'}
          {event.target_type && (
            <span className="muted-text"> · {event.target_type}</span>
          )}
        </td>
        <td>
          <span className={`status-pill audit-result-${event.result}`}>
            {event.result_label}
          </span>
        </td>
        <td className="date-cell">{event.ip_address || '—'}</td>
        <td>
          <button className="small-button" type="button" onClick={onToggle}>
            {expanded ? '收起' : '详情'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="audit-detail-row">
          <td colSpan={7}>
            <div className="audit-detail">
              <p>
                请求编号：<code>{event.request_id || '—'}</code>
                {' · '}
                对象编号：<code>{event.target_id ?? '—'}</code>
              </p>
              <pre>{JSON.stringify(event.detail ?? {}, null, 2)}</pre>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

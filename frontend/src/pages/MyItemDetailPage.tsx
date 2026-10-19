import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ApiError,
  vaultApi,
  type MyVaultItem,
} from '../api/client'
import { AppShell } from '../components/AppShell'
import { UserContentSection } from '../components/UserContentSection'
import { VaultGate } from '../components/VaultGate'

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

export function MyItemDetailPage() {
  const params = useParams<{ itemId: string }>()
  const itemId = Number(params.itemId)

  const [item, setItem] = useState<MyVaultItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!Number.isInteger(itemId) || itemId <= 0) {
      // Invalid route parameter: show the not-found state immediately.
      // oxlint-disable-next-line react/set-state-in-effect
      setError('找不到这条内容。')
      setLoading(false)
      return
    }
    const load = async () => {
      try {
        const data = await vaultApi.getMyItem(itemId)
        setItem(data)
      } catch (loadError) {
        if (loadError instanceof ApiError && loadError.status === 404) {
          setError('找不到这条内容，或你没有访问权限。')
        } else {
          setError(messageOf(loadError))
        }
      } finally {
        setLoading(false)
      }
    }
    // State updates occur after the async request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
  }, [itemId])

  if (loading) {
    return (
      <AppShell active="my-items">
        <p className="empty-state">正在加载…</p>
      </AppShell>
    )
  }

  if (!item) {
    return (
      <AppShell active="my-items">
        <section className="panel">
          <h2>找不到这条内容</h2>
          <p>{error}</p>
          <Link className="primary-link" to="/items">
            返回我的内容
          </Link>
        </section>
      </AppShell>
    )
  }

  return (
    <AppShell active="my-items">
      <section className="page-heading">
        <div>
          <p className="eyebrow">
            <Link className="text-link" to="/items">
              我的内容
            </Link>{' '}
            / 详情
          </p>
          <h1>{item.title}</h1>
          <p className="lede">{item.description || '没有填写说明。'}</p>
          <div className="tag-row">
            <span className="role-badge">{item.item_type_label}</span>
            <span className="stage-badge">
              所有者：{item.owner.display_name}
            </span>
          </div>
        </div>
      </section>

      <VaultGate>
        <UserContentSection item={item} />
      </VaultGate>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>条目信息</h2>
            <p>你能看到这些信息，说明当前账号有这条内容的访问权。</p>
          </div>
        </div>
        <dl className="info-list">
          <div>
            <dt>类型</dt>
            <dd>{item.item_type_label}</dd>
          </div>
          <div>
            <dt>所有者</dt>
            <dd>
              {item.owner.display_name}（@{item.owner.username}）
            </dd>
          </div>
          <div>
            <dt>创建时间</dt>
            <dd>{formatDate(item.created_at)}</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{formatDate(item.updated_at)}</dd>
          </div>
        </dl>
      </section>
    </AppShell>
  )
}

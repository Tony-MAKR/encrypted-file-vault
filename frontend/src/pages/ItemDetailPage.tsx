import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ApiError,
  adminApi,
  type ItemOptions,
  type User,
  type VaultGroupSummary,
  type VaultItemDetail,
} from '../api/client'
import { AdminContentSection } from '../components/AdminContentSection'
import { AppShell } from '../components/AppShell'
import { FormField } from '../components/FormField'
import { PurgeDialog } from '../components/PurgeDialog'
import { TagsInput } from '../components/TagsInput'
import { TextareaField } from '../components/TextareaField'
import { VaultGate } from '../components/VaultGate'

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后再试。'
}

function formatDate(value: string | null): string {
  if (!value) {
    return '—'
  }
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ItemDetailPage() {
  const params = useParams<{ itemId: string }>()
  const navigate = useNavigate()
  const itemId = Number(params.itemId)

  const [item, setItem] = useState<VaultItemDetail | null>(null)
  const [groups, setGroups] = useState<VaultGroupSummary[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [itemOptions, setItemOptions] = useState<ItemOptions>({
    categories: [],
    tags: [],
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [editForm, setEditForm] = useState({
    title: '',
    description: '',
    category: '',
    tags: [] as string[],
  })
  const [savingMeta, setSavingMeta] = useState(false)
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([])
  const [selectedOwnerId, setSelectedOwnerId] = useState('')
  const [busyAction, setBusyAction] = useState('')
  const [purgeOpen, setPurgeOpen] = useState(false)

  useEffect(() => {
    if (!Number.isInteger(itemId) || itemId <= 0) {
      // Invalid route parameter: show the not-found state immediately.
      // oxlint-disable-next-line react/set-state-in-effect
      setError('内容条目地址无效。')
      setLoading(false)
      return
    }

    const bootstrap = async () => {
      try {
        const [itemData, groupData, userData, options] =
          await Promise.all([
            adminApi.getItem(itemId),
            adminApi.listGroups({ page: 1, pageSize: 100 }),
            adminApi.listUsers({ page: 1, pageSize: 100 }),
            adminApi.itemOptions(),
          ])
        setItem(itemData)
        setEditForm({
          title: itemData.title,
          description: itemData.description,
          category: itemData.category,
          tags: itemData.tags,
        })
        setGroups(groupData.results)
        setUsers(userData.results)
        setItemOptions(options)
      } catch (loadError) {
        if (loadError instanceof ApiError && loadError.status === 404) {
          setError('找不到这条内容，或被删除了。')
        } else {
          setError(messageOf(loadError))
        }
      } finally {
        setLoading(false)
      }
    }

    // State updates occur after the async requests resolve.
    // oxlint-disable-next-line react/set-state-in-effect
    void bootstrap()
  }, [itemId])

  const refreshItem = async () => {
    const data = await adminApi.getItem(itemId)
    setItem(data)
  }

  const saveMetadata = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!item) {
      return
    }
    setSavingMeta(true)
    setError('')
    setNotice('')
    try {
      const data = await adminApi.updateItem(item.id, {
        title: editForm.title.trim(),
        description: editForm.description.trim(),
        category: editForm.category.trim(),
        tags: editForm.tags,
      })
      setItem(data)
      setEditForm({
        title: data.title,
        description: data.description,
        category: data.category,
        tags: data.tags,
      })
      setNotice('条目标题和说明已保存。')
    } catch (saveError) {
      setError(messageOf(saveError))
    } finally {
      setSavingMeta(false)
    }
  }

  const addGroupGrants = async () => {
    if (!item || selectedGroupIds.length === 0) {
      return
    }
    setBusyAction('add-group-grants')
    setError('')
    setNotice('')
    try {
      const result = await adminApi.addGroupGrants(item.id, selectedGroupIds)
      setNotice(
        result.added.length > 0
          ? `已授权 ${result.added.length} 个用户组，组内成员现在可以查看。`
          : '所选用户组已经有授权，没有重复添加。',
      )
      setSelectedGroupIds([])
      await refreshItem()
    } catch (grantError) {
      setError(messageOf(grantError))
    } finally {
      setBusyAction('')
    }
  }

  const removeGroupGrant = async (groupId: number, groupName: string) => {
    if (!item) {
      return
    }
    if (
      !window.confirm(
        `确定撤销“${groupName}”的授权吗？该组所有成员会立即失去这条内容的访问权，个人授权仍然保留。`,
      )
    ) {
      return
    }
    setBusyAction(`remove-group-${groupId}`)
    setError('')
    setNotice('')
    try {
      await adminApi.removeGroupGrant(item.id, groupId)
      setNotice(`已撤销用户组“${groupName}”的授权。`)
      await refreshItem()
    } catch (grantError) {
      setError(messageOf(grantError))
    } finally {
      setBusyAction('')
    }
  }

  const addUserGrants = async () => {
    if (!item || selectedUserIds.length === 0) {
      return
    }
    setBusyAction('add-user-grants')
    setError('')
    setNotice('')
    try {
      const result = await adminApi.addUserGrants(item.id, selectedUserIds)
      setNotice(
        result.added.length > 0
          ? `已单独授权 ${result.added.length} 位用户。`
          : '所选用户已经有授权，没有重复添加。',
      )
      setSelectedUserIds([])
      await refreshItem()
    } catch (grantError) {
      setError(messageOf(grantError))
    } finally {
      setBusyAction('')
    }
  }

  const removeUserGrant = async (userId: number, displayName: string) => {
    if (!item) {
      return
    }
    if (
      !window.confirm(
        `确定撤销 ${displayName} 的个人授权吗？如果对方仍在你授权的用户组里，仍可通过组访问。`,
      )
    ) {
      return
    }
    setBusyAction(`remove-user-${userId}`)
    setError('')
    setNotice('')
    try {
      await adminApi.removeUserGrant(item.id, userId)
      setNotice(`已撤销 ${displayName} 的个人授权。`)
      await refreshItem()
    } catch (grantError) {
      setError(messageOf(grantError))
    } finally {
      setBusyAction('')
    }
  }

  const trashItem = async () => {
    if (!item) {
      return
    }
    if (
      !window.confirm(
        '确定把这条内容删除到回收站吗？普通用户会立即看不到；管理员可在 30 天内恢复。',
      )
    ) {
      return
    }
    setBusyAction('trash')
    setError('')
    setNotice('')
    try {
      const data = await adminApi.trashItem(item.id)
      setItem(data)
      setNotice('条目已移入回收站，30 天内可以恢复。')
    } catch (trashError) {
      setError(messageOf(trashError))
    } finally {
      setBusyAction('')
    }
  }

  const restoreItem = async () => {
    if (!item) {
      return
    }
    setBusyAction('restore')
    setError('')
    setNotice('')
    try {
      const data = await adminApi.restoreItem(item.id)
      setItem(data)
      setNotice('条目已从回收站恢复。')
    } catch (restoreError) {
      setError(messageOf(restoreError))
    } finally {
      setBusyAction('')
    }
  }

  const toggleArchive = async () => {
    if (!item) {
      return
    }
    const willArchive = !item.is_archived
    if (
      !window.confirm(
        willArchive
          ? '归档后，这条内容会从普通用户的可见列表中消失。确定归档吗？'
          : '恢复后，被授权的普通用户会重新看到这条内容。确定恢复吗？',
      )
    ) {
      return
    }
    setBusyAction('archive')
    setError('')
    setNotice('')
    try {
      const data = willArchive
        ? await adminApi.archiveItem(item.id)
        : await adminApi.unarchiveItem(item.id)
      setItem(data)
      setNotice(willArchive ? '条目已归档。' : '条目已恢复。')
    } catch (archiveError) {
      setError(messageOf(archiveError))
    } finally {
      setBusyAction('')
    }
  }

  const transferOwner = async () => {
    if (!item || !selectedOwnerId) {
      return
    }
    const target = users.find(
      (user) => user.id === Number(selectedOwnerId),
    )
    if (!target) {
      return
    }
    if (
      !window.confirm(
        `确定把所有权转给 ${target.display_name} 吗？原所有者会失去“所有者自动访问”，除非另有授权。`,
      )
    ) {
      return
    }
    setBusyAction('transfer-owner')
    setError('')
    setNotice('')
    try {
      const data = await adminApi.transferOwner(item.id, target.id)
      setItem(data)
      setSelectedOwnerId('')
      setNotice(`所有权已转给 ${target.display_name}。`)
    } catch (ownerError) {
      setError(messageOf(ownerError))
    } finally {
      setBusyAction('')
    }
  }

  if (loading) {
    return (
      <AppShell active="items">
        <p className="empty-state">正在加载内容条目…</p>
      </AppShell>
    )
  }

  if (!item) {
    return (
      <AppShell active="items">
        <section className="panel">
          <h2>找不到这条内容</h2>
          <p>{error || '内容条目不存在，或已经被删除。'}</p>
          <Link className="primary-link" to="/admin/items">
            返回内容条目列表
          </Link>
        </section>
      </AppShell>
    )
  }

  const grantedGroupIds = new Set(
    item.group_grants.map((grant) => grant.group_id),
  )
  const groupOptions = groups.filter(
    (group) => !grantedGroupIds.has(group.id),
  )
  const grantedUserIds = new Set(
    item.user_grants.map((grant) => grant.user_id),
  )
  const userOptions = users.filter(
    (user) =>
      user.is_active &&
      user.id !== item.owner.id &&
      !grantedUserIds.has(user.id),
  )
  const ownerOptions = users.filter(
    (user) =>
      user.is_active && user.role === 'admin' && user.id !== item.owner.id,
  )

  return (
    <AppShell active="items">
      <section className="page-heading">
        <div>
          <p className="eyebrow">
            <Link className="text-link" to="/admin/items">
              内容条目
            </Link>{' '}
            / 授权面板
          </p>
          <h1>{item.title}</h1>
          <p className="lede">
            {item.description || '没有填写说明。'}
          </p>
          <div className="tag-row">
            <span className="role-badge">{item.item_type_label}</span>
            <span className="stage-badge">
              所有者：{item.owner.display_name}
            </span>
            <span className="stage-badge">
              {item.is_deleted
                ? '回收站'
                : item.is_archived
                  ? '已归档'
                  : '活跃'}
            </span>
            {item.category && (
              <span className="stage-badge">分类：{item.category}</span>
            )}
            {item.tags.map((tag) => (
              <span className="tag-badge" key={tag}>
                {tag}
              </span>
            ))}
          </div>
        </div>
        <div className="row-actions">
          {item.is_deleted ? (
            <>
              <button
                className="primary-button"
                type="button"
                onClick={() => void restoreItem()}
                disabled={busyAction === 'restore'}
              >
                {busyAction === 'restore' ? '正在恢复…' : '从回收站恢复'}
              </button>
              <button
                className="danger-button"
                type="button"
                onClick={() => setPurgeOpen(true)}
              >
                永久删除
              </button>
            </>
          ) : (
            <>
              <button
                className="secondary-button"
                type="button"
                onClick={() => void toggleArchive()}
                disabled={busyAction === 'archive'}
              >
                {busyAction === 'archive'
                  ? '正在处理…'
                  : item.is_archived
                    ? '恢复条目'
                    : '归档条目'}
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => void trashItem()}
                disabled={busyAction === 'trash'}
              >
                {busyAction === 'trash' ? '正在删除…' : '删除到回收站'}
              </button>
            </>
          )}
        </div>
      </section>

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

      <VaultGate>
        <AdminContentSection item={item} onChanged={refreshItem} />
      </VaultGate>

      <div className="detail-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>标题与说明</h2>
              <p>类型创建后不能修改；授权关系不受标题修改影响。</p>
            </div>
          </div>
          <form
            className="form"
            onSubmit={(event) => void saveMetadata(event)}
          >
            <FormField
              label="标题"
              name="edit_item_title"
              value={editForm.title}
              onChange={(event) =>
                setEditForm((current) => ({
                  ...current,
                  title: event.target.value,
                }))
              }
              maxLength={120}
              required
            />
            <TextareaField
              label="说明"
              name="edit_item_description"
              value={editForm.description}
              onChange={(event) =>
                setEditForm((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
              maxLength={1000}
              rows={4}
              hint="说明是明文管理信息，不要写密码或秘密细节。"
            />
            <FormField
              label="分类"
              name="edit_item_category"
              value={editForm.category}
              onChange={(event) =>
                setEditForm((current) => ({
                  ...current,
                  category: event.target.value,
                }))
              }
              maxLength={50}
              list="edit-category-options"
              placeholder="例如：财务资料"
              hint="分类是明文，用于筛选；不要写密码。"
            />
            <datalist id="edit-category-options">
              {itemOptions.categories.map((category) => (
                <option value={category} key={category} />
              ))}
            </datalist>
            <TagsInput
              label="标签"
              value={editForm.tags}
              onChange={(tags) =>
                setEditForm((current) => ({ ...current, tags }))
              }
              hint="多个标签用于筛选；标签是明文，不要写密码或敏感细节。"
            />
            <div className="form-actions">
              <button
                className="primary-button"
                type="submit"
                disabled={savingMeta}
              >
                {savingMeta ? '正在保存…' : '保存修改'}
              </button>
            </div>
          </form>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>所有者与状态</h2>
              <p>所有者始终可以打开内容；其他管理员不会自动获得内容权限。</p>
            </div>
          </div>
          <dl className="info-list">
            <div>
              <dt>当前所有者</dt>
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
            <div>
              <dt>归档时间</dt>
              <dd>{formatDate(item.archived_at)}</dd>
            </div>
            <div>
              <dt>你的内容权限</dt>
              <dd>
                {item.can_open_content
                  ? '可以打开（所有者或已授权）'
                  : '仅能管理元数据，未获得内容权限'}
              </dd>
            </div>
          </dl>

          <div className="form">
            <div className="field">
              <label htmlFor="new_owner">转移所有权</label>
              <select
                id="new_owner"
                value={selectedOwnerId}
                onChange={(event) => setSelectedOwnerId(event.target.value)}
                disabled={ownerOptions.length === 0}
              >
                <option value="">选择另一位启用中的管理员</option>
                {ownerOptions.map((admin) => (
                  <option key={admin.id} value={admin.id}>
                    {admin.display_name}（@{admin.username}）
                  </option>
                ))}
              </select>
              <p className="field-hint">
                转移后原所有者会失去所有者自动访问，仍可能通过组或个人授权保留访问。
              </p>
            </div>
            <div className="form-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => void transferOwner()}
                disabled={
                  busyAction === 'transfer-owner' || !selectedOwnerId
                }
              >
                {busyAction === 'transfer-owner'
                  ? '正在转移…'
                  : '转移所有权'}
              </button>
            </div>
          </div>
        </section>
      </div>

      <div className="grant-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>按用户组授权</h2>
              <p>组内所有成员都能看到这条内容，成员变化立即生效。</p>
            </div>
          </div>

          {item.group_grants.length === 0 ? (
            <p className="empty-state">还没有授权给任何用户组。</p>
          ) : (
            <ul className="grant-list">
              {item.group_grants.map((grant) => (
                <li key={grant.id}>
                  <div>
                    <strong>{grant.group_name}</strong>
                    <small>
                      授权人：{grant.granted_by || '已停用账号'} ·{' '}
                      {formatDate(grant.created_at)}
                    </small>
                  </div>
                  <button
                    className="small-button"
                    type="button"
                    onClick={() =>
                      void removeGroupGrant(grant.group_id, grant.group_name)
                    }
                    disabled={
                      busyAction === `remove-group-${grant.group_id}`
                    }
                  >
                    撤销
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="grant-add-row">
            <label className="field-inline" htmlFor="add-group-grants">
              <span>授权给用户组</span>
              <select
                id="add-group-grants"
                multiple
                value={selectedGroupIds.map(String)}
                onChange={(event) =>
                  setSelectedGroupIds(
                    Array.from(
                      event.target.selectedOptions,
                      (option) => Number(option.value),
                    ),
                  )
                }
                size={Math.min(6, Math.max(2, groupOptions.length))}
                disabled={
                  busyAction === 'add-group-grants' ||
                  groupOptions.length === 0
                }
              >
                {groupOptions.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}（{group.member_count} 人）
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary-button"
              type="button"
              onClick={() => void addGroupGrants()}
              disabled={
                busyAction === 'add-group-grants' ||
                selectedGroupIds.length === 0
              }
            >
              {busyAction === 'add-group-grants'
                ? '正在授权…'
                : '授权所选组'}
            </button>
          </div>
          {groupOptions.length === 0 && (
            <p className="field-hint">
              没有可新增授权的用户组。可以在“用户组”页面创建。
            </p>
          )}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>单独授权用户</h2>
              <p>个人授权独立于用户组；被移出组后，个人授权仍然保留。</p>
            </div>
          </div>

          {item.user_grants.length === 0 ? (
            <p className="empty-state">还没有单独授权给任何用户。</p>
          ) : (
            <ul className="grant-list">
              {item.user_grants.map((grant) => (
                <li key={grant.id}>
                  <div>
                    <strong>{grant.display_name}</strong>
                    <small>
                      @{grant.username} · 授权人：{grant.granted_by || '已停用账号'} ·{' '}
                      {formatDate(grant.created_at)}
                    </small>
                  </div>
                  <button
                    className="small-button"
                    type="button"
                    onClick={() =>
                      void removeUserGrant(
                        grant.user_id,
                        grant.display_name,
                      )
                    }
                    disabled={busyAction === `remove-user-${grant.user_id}`}
                  >
                    撤销
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="grant-add-row">
            <label className="field-inline" htmlFor="add-user-grants">
              <span>授权给单个用户</span>
              <select
                id="add-user-grants"
                multiple
                value={selectedUserIds.map(String)}
                onChange={(event) =>
                  setSelectedUserIds(
                    Array.from(
                      event.target.selectedOptions,
                      (option) => Number(option.value),
                    ),
                  )
                }
                size={Math.min(6, Math.max(2, userOptions.length))}
                disabled={
                  busyAction === 'add-user-grants' ||
                  userOptions.length === 0
                }
              >
                {userOptions.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.display_name}（@{user.username}）
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary-button"
              type="button"
              onClick={() => void addUserGrants()}
              disabled={
                busyAction === 'add-user-grants' ||
                selectedUserIds.length === 0
              }
            >
              {busyAction === 'add-user-grants'
                ? '正在授权…'
                : '授权所选用户'}
            </button>
          </div>
          {userOptions.length === 0 && (
            <p className="field-hint">
              没有可新增授权的启用用户，或所有用户已经有授权。
            </p>
          )}
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>有效访问人预览（{item.effective_user_count} 人）</h2>
            <p>
              去重后的启用账号：所有者、个人授权和组授权的并集。管理员若未被授权，不会出现在这里。
            </p>
          </div>
        </div>
        {item.effective_users.length === 0 ? (
          <p className="empty-state">目前没有有效访问人。</p>
        ) : (
          <ul className="chip-list">
            {item.effective_users.map((user) => (
              <li className="member-chip" key={user.id}>
                <span>
                  <strong>{user.display_name}</strong>
                  <small>
                    @{user.username}
                    {user.id === item.owner.id ? ' · 所有者' : ''}
                  </small>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {purgeOpen && (
        <PurgeDialog
          item={item}
          onClose={() => setPurgeOpen(false)}
          onPurged={() => {
            setPurgeOpen(false)
            navigate('/admin/items', { replace: true })
          }}
        />
      )}
    </AppShell>
  )
}

import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  adminApi,
  type User,
  type VaultGroupDetail,
} from '../api/client'
import { AppShell } from '../components/AppShell'
import { FormField } from '../components/FormField'
import { TextareaField } from '../components/TextareaField'

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后再试。'
}

export function GroupDetailPage() {
  const params = useParams<{ groupId: string }>()
  const navigate = useNavigate()
  const groupId = Number(params.groupId)

  const [group, setGroup] = useState<VaultGroupDetail | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [editForm, setEditForm] = useState({ name: '', description: '' })
  const [saving, setSaving] = useState(false)

  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([])
  const [addingMembers, setAddingMembers] = useState(false)
  const [busyUserId, setBusyUserId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)

  const loadGroup = useCallback(async () => {
    if (!Number.isInteger(groupId) || groupId <= 0) {
      setError('用户组地址无效。')
      setLoading(false)
      return
    }
    try {
      const data = await adminApi.getGroup(groupId)
      setGroup(data)
      setEditForm({ name: data.name, description: data.description })
    } catch (loadError) {
      setError(messageOf(loadError))
    } finally {
      setLoading(false)
    }
  }, [groupId])

  const refreshGroup = async () => {
    const data = await adminApi.getGroup(groupId)
    setGroup(data)
  }

  useEffect(() => {
    // State updates occur after the async requests resolve.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadGroup()
    adminApi
      .listUsers({ page: 1, pageSize: 100 })
      .then((data) => setUsers(data.results))
      .catch(() => setUsers([]))
  }, [loadGroup])

  const memberIds = new Set(group?.members.map((member) => member.id) ?? [])
  const memberOptions = users.filter(
    (user) => user.is_active && !memberIds.has(user.id),
  )

  const saveGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!group) {
      return
    }
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await adminApi.updateGroup(group.id, {
        name: editForm.name.trim(),
        description: editForm.description.trim(),
      })
      setNotice('用户组信息已保存。')
      await loadGroup()
    } catch (saveError) {
      setError(messageOf(saveError))
    } finally {
      setSaving(false)
    }
  }

  const addMembers = async () => {
    if (!group || selectedUserIds.length === 0) {
      return
    }
    setAddingMembers(true)
    setError('')
    setNotice('')
    try {
      const result = await adminApi.addGroupMembers(
        group.id,
        selectedUserIds,
      )
      const parts: string[] = []
      if (result.added.length > 0) {
        parts.push(`已加入 ${result.added.length} 位用户`)
      }
      if (result.already_members.length > 0) {
        parts.push(`${result.already_members.length} 位用户本来就在组内`)
      }
      setNotice(parts.join('；') || '所选用户已经在组内。')
      setSelectedUserIds([])
      await refreshGroup()
    } catch (addError) {
      setError(messageOf(addError))
    } finally {
      setAddingMembers(false)
    }
  }

  const removeMember = async (userId: number, displayName: string) => {
    if (!group) {
      return
    }
    if (
      !window.confirm(
        `确定把 ${displayName} 移出“${group.name}”吗？该用户通过这个组获得的访问权会立即消失，个人授权仍然保留。`,
      )
    ) {
      return
    }
    setBusyUserId(userId)
    setError('')
    setNotice('')
    try {
      await adminApi.removeGroupMember(group.id, userId)
      setNotice(`已把 ${displayName} 移出用户组。`)
      await refreshGroup()
    } catch (removeError) {
      setError(messageOf(removeError))
    } finally {
      setBusyUserId(null)
    }
  }

  const deleteGroup = async () => {
    if (!group) {
      return
    }
    if (group.granted_item_count > 0) {
      setError(
        `“${group.name}”仍被 ${group.granted_item_count} 条内容授权，请先到条目详情撤销授权。`,
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
    setDeleting(true)
    setError('')
    try {
      await adminApi.deleteGroup(group.id)
      navigate('/admin/groups', { replace: true })
    } catch (deleteError) {
      setError(messageOf(deleteError))
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <AppShell active="groups">
        <p className="empty-state">正在加载用户组…</p>
      </AppShell>
    )
  }

  if (!group) {
    return (
      <AppShell active="groups">
        <section className="panel">
          <h2>找不到这个用户组</h2>
          <p>{error || '用户组不存在，或已经被删除。'}</p>
          <Link className="primary-link" to="/admin/groups">
            返回用户组列表
          </Link>
        </section>
      </AppShell>
    )
  }

  return (
    <AppShell active="groups">
      <section className="page-heading">
        <div>
          <p className="eyebrow">
            <Link className="text-link" to="/admin/groups">
              用户组
            </Link>{' '}
            / 详情
          </p>
          <h1>{group.name}</h1>
          <p className="lede">
            {group.description || '没有填写说明。'} 组内成员会共享这个组获得的授权。
          </p>
          <div className="tag-row">
            <span className="role-badge">{group.member_count} 位成员</span>
            <span className="stage-badge">
              {group.granted_item_count} 条内容授权
            </span>
          </div>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={() => void deleteGroup()}
          disabled={deleting || group.granted_item_count > 0}
          title={
            group.granted_item_count > 0
              ? `仍被 ${group.granted_item_count} 条内容授权，需先撤销`
              : '删除这个用户组'
          }
        >
          {deleting ? '正在删除…' : '删除用户组'}
        </button>
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

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>组信息</h2>
            <p>修改名称或说明不会影响成员和已有授权。</p>
          </div>
        </div>
        <form
          className="form form-grid"
          onSubmit={(event) => void saveGroup(event)}
        >
          <FormField
            label="用户组名称"
            name="edit_group_name"
            value={editForm.name}
            onChange={(event) =>
              setEditForm((current) => ({
                ...current,
                name: event.target.value,
              }))
            }
            maxLength={50}
            required
          />
          <TextareaField
            label="说明"
            name="edit_group_description"
            value={editForm.description}
            onChange={(event) =>
              setEditForm((current) => ({
                ...current,
                description: event.target.value,
              }))
            }
            maxLength={500}
            rows={3}
          />
          <div className="form-actions form-span-all">
            <button
              className="primary-button"
              type="submit"
              disabled={saving}
            >
              {saving ? '正在保存…' : '保存组信息'}
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>组成员</h2>
            <p>
              只能加入启用中的账号。移出成员会立即撤销该用户通过这个组获得的访问权。
            </p>
          </div>
        </div>

        {group.members.length === 0 ? (
          <p className="empty-state">这个组还没有成员。</p>
        ) : (
          <ul className="chip-list">
            {group.members.map((member) => (
              <li className="member-chip" key={member.id}>
                <span>
                  <strong>{member.display_name}</strong>
                  <small>@{member.username}</small>
                </span>
                <button
                  className="small-button"
                  type="button"
                  onClick={() =>
                    void removeMember(member.id, member.display_name)
                  }
                  disabled={busyUserId === member.id}
                >
                  {busyUserId === member.id ? '正在移出…' : '移出'}
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="grant-add-row">
          <label className="field-inline" htmlFor="add-members">
            <span>加入用户</span>
            <select
              id="add-members"
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
              size={Math.min(6, Math.max(2, memberOptions.length))}
              disabled={addingMembers || memberOptions.length === 0}
            >
              {memberOptions.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name}（@{user.username}）
                </option>
              ))}
            </select>
          </label>
          <button
            className="primary-button"
            type="button"
            onClick={() => void addMembers()}
            disabled={addingMembers || selectedUserIds.length === 0}
          >
            {addingMembers ? '正在加入…' : '加入所选用户'}
          </button>
        </div>
        {memberOptions.length === 0 && (
          <p className="field-hint">
            没有可加入的启用用户。请先在“用户管理”里创建或启用账号。
          </p>
        )}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>这个组能访问的内容</h2>
            <p>授权前先核对，避免把内容发给不该看的人。</p>
          </div>
        </div>
        {group.granted_items.length === 0 ? (
          <p className="empty-state">这个组还没有被授权任何内容。</p>
        ) : (
          <ul className="grant-items">
            {group.granted_items.map((item) => (
              <li key={item.id}>
                <Link className="text-link" to={`/admin/items/${item.id}`}>
                  {item.title}
                </Link>
                <span className="muted-text">{item.item_type_label}</span>
                {item.is_archived && (
                  <span className="status-pill status-off">已归档</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {group.granted_item_count > 0 && (
        <section className="panel notice-panel">
          <h2>删除保护</h2>
          <p>
            这个组仍被 {group.granted_item_count}{' '}
            条内容授权。为避免一批用户突然失去访问，必须先到对应条目的授权面板撤销组授权，才能删除用户组。
          </p>
        </section>
      )}
    </AppShell>
  )
}

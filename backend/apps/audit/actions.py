"""Audit action names, labels and filter categories.

Keep this list small and stable: the UI shows these labels, and later versions
may use the values for reporting. Never put secrets in labels or details.
"""

from __future__ import annotations

CATEGORY_LABELS: dict[str, str] = {
    "auth": "登录与账号",
    "vault": "保险箱",
    "users": "用户管理",
    "groups": "用户组",
    "items": "条目",
    "grants": "授权",
    "content": "内容查看",
    "backup": "备份与恢复",
    "audit": "审计",
}

# action -> (label, category)
ACTION_CATALOG: dict[str, tuple[str, str]] = {
    # Authentication and setup
    "login_succeeded": ("登录成功", "auth"),
    "login_failed": ("登录失败", "auth"),
    "login_blocked": ("登录被锁定", "auth"),
    "logout": ("退出登录", "auth"),
    "password_changed": ("修改自己的密码", "auth"),
    "setup_completed": ("完成首次设置", "auth"),
    # Vault key state
    "vault_initialized": ("设置主密码", "vault"),
    "vault_unlocked": ("解锁保险箱", "vault"),
    "vault_unlock_failed": ("解锁失败", "vault"),
    "vault_locked": ("锁定保险箱", "vault"),
    # User administration
    "user_created": ("创建用户", "users"),
    "user_updated": ("修改用户资料", "users"),
    "user_role_changed": ("修改用户角色", "users"),
    "user_disabled": ("停用用户", "users"),
    "user_enabled": ("启用用户", "users"),
    "user_unlocked": ("解锁用户账号", "users"),
    "user_password_reset": ("重置用户密码", "users"),
    # Groups
    "group_created": ("创建用户组", "groups"),
    "group_updated": ("修改用户组", "groups"),
    "group_deleted": ("删除用户组", "groups"),
    "group_member_added": ("添加组员", "groups"),
    "group_member_removed": ("移出组员", "groups"),
    # Items
    "item_created": ("创建条目", "items"),
    "item_updated": ("修改条目", "items"),
    "item_archived": ("归档条目", "items"),
    "item_unarchived": ("取消归档", "items"),
    "item_owner_changed": ("转移条目所有者", "items"),
    "item_trashed": ("删除到回收站", "items"),
    "item_restored": ("从回收站恢复", "items"),
    "item_purged": ("永久删除条目", "items"),
    # Grants
    "grant_group_added": ("添加用户组授权", "grants"),
    "grant_group_removed": ("撤销用户组授权", "grants"),
    "grant_user_added": ("添加个人授权", "grants"),
    "grant_user_removed": ("撤销个人授权", "grants"),
    # Content access
    "text_saved": ("保存文字秘密", "content"),
    "file_uploaded": ("上传加密文件", "content"),
    "text_viewed": ("查看文字条目", "content"),
    "text_revealed": ("显示密码", "content"),
    "text_copied": ("复制密码", "content"),
    "file_downloaded": ("下载解密文件", "content"),
    # Backup and restore
    "backup_created": ("创建加密备份", "backup"),
    "backup_verified": ("验证加密备份", "backup"),
    "backup_verify_failed": ("备份验证失败", "backup"),
    "backup_restored": ("从备份恢复", "backup"),
    # Audit
    "audit_viewed": ("查询审计记录", "audit"),
    "audit_pruned": ("清理过期审计记录", "audit"),
}

RESULT_LABELS: dict[str, str] = {
    "success": "成功",
    "failure": "失败",
    "denied": "被拒绝",
}

CATEGORY_ACTIONS: dict[str, list[str]] = {}
for _action, (_label, _category) in ACTION_CATALOG.items():
    CATEGORY_ACTIONS.setdefault(_category, []).append(_action)


def action_label(action: str) -> str:
    return ACTION_CATALOG.get(action, (action, ""))[0] if action else ""


def action_category(action: str) -> str:
    return ACTION_CATALOG.get(action, ("", ""))[1]

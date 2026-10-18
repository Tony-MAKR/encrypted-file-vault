"""Authorization rules for vault items.

Effective access is always the union of three independent sources:

* the item owner,
* a grant addressed directly to the user,
* a grant addressed to a group the user belongs to.

There are deliberately no deny rules and no permission cache. Every request
queries the current state, so revoking a grant or removing a member takes
effect on the next request.
"""

from __future__ import annotations

from django.db.models import Q

from apps.accounts.models import User

from .models import GroupGrant, UserGrant, VaultItem


def is_active_admin(user: User | None) -> bool:
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.role == User.Role.ADMIN
    )


def access_filter(user: User) -> Q:
    """Q object matching items this user can open through ownership/grants."""

    return (
        Q(owner=user)
        | Q(user_grants__user=user)
        | Q(group_grants__group__memberships__user=user)
    )


def accessible_items(user: User, include_archived: bool = False):
    """Items the user may open, without duplicates."""

    queryset = VaultItem.objects.filter(access_filter(user))
    if not include_archived:
        queryset = queryset.filter(is_archived=False)
    return queryset.distinct()


def can_open_content(user: User | None, item: VaultItem) -> bool:
    """Return whether the user may decrypt/open the item's real content.

    Administrators do not bypass this check. An administrator who is neither
    the owner nor granted access can manage metadata but not content.
    """

    if not user or not user.is_authenticated or not user.is_active:
        return False
    if item.owner_id == user.pk:
        return True
    if UserGrant.objects.filter(item=item, user=user).exists():
        return True
    return GroupGrant.objects.filter(
        item=item, group__memberships__user=user
    ).exists()


def can_view_metadata(user: User | None, item: VaultItem) -> bool:
    """Administrators see all metadata; other users need actual access."""

    if not user or not user.is_authenticated or not user.is_active:
        return False
    return is_active_admin(user) or can_open_content(user, item)


def effective_users_for_item(item: VaultItem):
    """Enabled accounts that can open the item, de-duplicated and sorted."""

    return (
        User.objects.filter(
            Q(pk=item.owner_id)
            | Q(vault_user_grants__item=item)
            | Q(vault_group_memberships__group__grants__item=item),
            is_active=True,
        )
        .distinct()
        .order_by("username")
    )

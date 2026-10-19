"""Administrator endpoints for groups, item metadata and grants."""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsAdminRole

from .content_services import maybe_purge_expired_items
from .models import (
    GroupGrant,
    GroupMembership,
    UserGrant,
    VaultContent,
    VaultGroup,
    VaultItem,
)
from .pagination import VaultPagination
from .serializers import (
    GroupCreateSerializer,
    GroupDetailSerializer,
    GroupIdsSerializer,
    GroupSerializer,
    GroupUpdateSerializer,
    ItemCreateSerializer,
    ItemDetailSerializer,
    ItemListSerializer,
    ItemUpdateSerializer,
    OwnerTransferSerializer,
    UserBriefSerializer,
    UserIdsSerializer,
)
from .services import is_active_admin

logger = logging.getLogger("apps.vault")


def _group_with_related(group_id: int) -> VaultGroup:
    return get_object_or_404(
        VaultGroup.objects.select_related("created_by").prefetch_related(
            "memberships__user", "grants__item"
        ),
        pk=group_id,
    )


def _item_with_related(item_id: int) -> VaultItem:
    return get_object_or_404(
        VaultItem.objects.select_related("owner", "content").prefetch_related(
            "group_grants__group",
            "group_grants__granted_by",
            "user_grants__user",
            "user_grants__granted_by",
        ),
        pk=item_id,
    )


def _deleted_error() -> Response:
    return Response(
        {
            "detail": "这条条目在回收站中，请先恢复后再操作。",
            "code": "item_deleted",
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _group_conflict(group: VaultGroup) -> Response:
    affected = group.grants.count()
    return Response(
        {
            "detail": (
                f"该用户组仍被 {affected} 条内容授权，请先撤销这些授权再删除。"
            ),
            "code": "group_has_grants",
            "affected_item_count": affected,
        },
        status=status.HTTP_409_CONFLICT,
    )


# ---------------------------------------------------------------------------
# Groups and members
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_groups(request):
    if request.method == "GET":
        search = (request.query_params.get("q") or "").strip()[:50]
        queryset = (
            VaultGroup.objects.select_related("created_by")
            .annotate(
                member_count=Count("memberships", distinct=True),
                granted_item_count=Count("grants", distinct=True),
            )
            .order_by("name")
        )
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        paginator = VaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=admin_groups)
        serializer = GroupSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = GroupCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        group = VaultGroup.objects.create(
            name=data["name"],
            description=data.get("description", ""),
            created_by=request.user,
        )
    except IntegrityError:
        return Response(
            {"name": ["这个用户组名称已经被使用。"]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    logger.info(
        "group_created actor=%s group_id=%s", request.user.username, group.pk
    )
    return Response(
        GroupDetailSerializer(_group_with_related(group.pk)).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_group_detail(request, group_id: int):
    group = _group_with_related(group_id)

    if request.method == "GET":
        return Response(GroupDetailSerializer(group).data)

    if request.method == "PATCH":
        serializer = GroupUpdateSerializer(
            group, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(group, field, value)
        try:
            group.save()
        except IntegrityError:
            return Response(
                {"name": ["这个用户组名称已经被使用。"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info(
            "group_updated actor=%s group_id=%s fields=%s",
            request.user.username,
            group.pk,
            ",".join(sorted(serializer.validated_data)),
        )
        return Response(
            GroupDetailSerializer(_group_with_related(group.pk)).data
        )

    if group.grants.exists():
        return _group_conflict(group)

    group_name = group.name
    try:
        with transaction.atomic():
            group.delete()
    except ProtectedError:
        # Another request added a grant between the check and the delete.
        return _group_conflict(group)

    logger.info(
        "group_deleted actor=%s group_id=%s group_name=%s",
        request.user.username,
        group_id,
        group_name,
    )
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_group_members(request, group_id: int):
    group = get_object_or_404(VaultGroup, pk=group_id)
    serializer = UserIdsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user_ids = serializer.validated_data["user_ids"]

    users = list(User.objects.filter(pk__in=user_ids).order_by("username"))
    found_ids = {user.pk for user in users}
    missing = [user_id for user_id in user_ids if user_id not in found_ids]
    if missing:
        return Response(
            {
                "detail": "部分用户不存在。",
                "code": "unknown_users",
                "user_ids": missing,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    inactive = [user.pk for user in users if not user.is_active]
    if inactive:
        return Response(
            {
                "detail": "只能把启用中的用户加入用户组。",
                "code": "inactive_users",
                "user_ids": inactive,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing = set(
        GroupMembership.objects.filter(
            group=group, user_id__in=user_ids
        ).values_list("user_id", flat=True)
    )
    added: list[User] = []
    with transaction.atomic():
        for user in users:
            if user.pk in existing:
                continue
            GroupMembership.objects.create(
                group=group, user=user, added_by=request.user
            )
            added.append(user)
            logger.info(
                "group_member_added actor=%s group_id=%s target=%s",
                request.user.username,
                group.pk,
                user.username,
            )

    return Response(
        {
            "added": UserBriefSerializer(added, many=True).data,
            "already_members": sorted(existing),
            "member_count": group.memberships.count(),
        }
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_group_member_detail(request, group_id: int, user_id: int):
    membership = GroupMembership.objects.filter(
        group_id=group_id, user_id=user_id
    ).first()
    if membership is not None:
        username = membership.user.username
        membership.delete()
        logger.info(
            "group_member_removed actor=%s group_id=%s target=%s",
            request.user.username,
            group_id,
            username,
        )
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Items and grants
# ---------------------------------------------------------------------------


def _apply_archived_filter(queryset, request):
    value = (request.query_params.get("archived") or "active").strip().lower()
    if value == "all":
        return queryset
    if value in {"true", "1", "yes", "archived"}:
        return queryset.filter(is_archived=True)
    return queryset.filter(is_archived=False)


def _apply_deleted_filter(queryset, request):
    value = (request.query_params.get("deleted") or "active").strip().lower()
    if value == "all":
        return queryset
    if value in {"true", "1", "yes", "only", "deleted", "trash"}:
        return queryset.filter(is_deleted=True)
    return queryset.filter(is_deleted=False)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_items(request):
    if request.method == "GET":
        maybe_purge_expired_items()
        search = (request.query_params.get("q") or "").strip()[:50]
        item_type = (request.query_params.get("item_type") or "").strip()
        queryset = (
            VaultItem.objects.select_related("owner")
            .annotate(
                group_grant_count=Count("group_grants", distinct=True),
                user_grant_count=Count("user_grants", distinct=True),
                has_content=Exists(
                    VaultContent.objects.filter(item_id=OuterRef("pk"))
                ),
            )
            .order_by("-created_at", "-id")
        )
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        if item_type in VaultItem.ItemType.values:
            queryset = queryset.filter(item_type=item_type)
        queryset = _apply_deleted_filter(queryset, request)
        queryset = _apply_archived_filter(queryset, request)

        paginator = VaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=admin_items)
        serializer = ItemListSerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)

    serializer = ItemCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    item = VaultItem.objects.create(
        title=data["title"],
        item_type=data["item_type"],
        description=data.get("description", ""),
        owner=request.user,
    )
    logger.info(
        "item_created actor=%s item_id=%s owner=%s item_type=%s",
        request.user.username,
        item.pk,
        request.user.username,
        item.item_type,
    )
    return Response(
        ItemDetailSerializer(
            _item_with_related(item.pk), context={"request": request}
        ).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_detail(request, item_id: int):
    item = _item_with_related(item_id)

    if request.method == "GET":
        return Response(
            ItemDetailSerializer(
                item, context={"request": request}
            ).data
        )

    if item.is_deleted:
        return _deleted_error()

    serializer = ItemUpdateSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    for field, value in serializer.validated_data.items():
        setattr(item, field, value)
    item.save(
        update_fields=[*serializer.validated_data.keys(), "updated_at"]
    )
    logger.info(
        "item_updated actor=%s item_id=%s fields=%s",
        request.user.username,
        item.pk,
        ",".join(sorted(serializer.validated_data)),
    )
    return Response(
        ItemDetailSerializer(
            _item_with_related(item.pk), context={"request": request}
        ).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_archive(request, item_id: int):
    item = get_object_or_404(VaultItem, pk=item_id)
    if item.is_deleted:
        return _deleted_error()
    if not item.is_archived:
        item.is_archived = True
        item.archived_at = timezone.now()
        item.save(update_fields=["is_archived", "archived_at", "updated_at"])
        logger.info(
            "item_archived actor=%s item_id=%s",
            request.user.username,
            item.pk,
        )
    return Response(
        ItemDetailSerializer(
            _item_with_related(item.pk), context={"request": request}
        ).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_unarchive(request, item_id: int):
    item = get_object_or_404(VaultItem, pk=item_id)
    if item.is_deleted:
        return _deleted_error()
    if item.is_archived:
        item.is_archived = False
        item.archived_at = None
        item.save(update_fields=["is_archived", "archived_at", "updated_at"])
        logger.info(
            "item_unarchived actor=%s item_id=%s",
            request.user.username,
            item.pk,
        )
    return Response(
        ItemDetailSerializer(
            _item_with_related(item.pk), context={"request": request}
        ).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_owner(request, item_id: int):
    item = get_object_or_404(VaultItem.objects.select_related("owner"), pk=item_id)
    if item.is_deleted:
        return _deleted_error()
    serializer = OwnerTransferSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    owner_id = serializer.validated_data["owner_id"]

    target = User.objects.filter(pk=owner_id).first()
    if target is None:
        return Response(
            {"detail": "目标用户不存在。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not is_active_admin(target):
        return Response(
            {"detail": "新所有者必须是启用中的管理员。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if target.pk == item.owner_id:
        return Response(
            {"detail": "这名管理员已经是该条目的所有者。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    old_owner = item.owner
    item.owner = target
    item.save(update_fields=["owner", "updated_at"])
    logger.info(
        "item_owner_transferred actor=%s item_id=%s old_owner=%s new_owner=%s",
        request.user.username,
        item.pk,
        old_owner.username,
        target.username,
    )
    return Response(
        ItemDetailSerializer(
            _item_with_related(item.pk), context={"request": request}
        ).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_group_grants(request, item_id: int):
    item = get_object_or_404(VaultItem, pk=item_id)
    if item.is_deleted:
        return _deleted_error()
    serializer = GroupIdsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    group_ids = serializer.validated_data["group_ids"]

    groups = list(VaultGroup.objects.filter(pk__in=group_ids).order_by("name"))
    found_ids = {group.pk for group in groups}
    missing = [group_id for group_id in group_ids if group_id not in found_ids]
    if missing:
        return Response(
            {
                "detail": "部分用户组不存在。",
                "code": "unknown_groups",
                "group_ids": missing,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing = set(
        GroupGrant.objects.filter(item=item, group_id__in=group_ids).values_list(
            "group_id", flat=True
        )
    )
    added: list[int] = []
    with transaction.atomic():
        for group in groups:
            if group.pk in existing:
                continue
            GroupGrant.objects.create(
                item=item, group=group, granted_by=request.user
            )
            added.append(group.pk)
            logger.info(
                "group_grant_added actor=%s item_id=%s group_id=%s",
                request.user.username,
                item.pk,
                group.pk,
            )

    return Response(
        {
            "added": added,
            "already_granted": sorted(existing),
            "grant_count": item.group_grants.count(),
        },
        status=status.HTTP_201_CREATED if added else status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_group_grant_detail(request, item_id: int, group_id: int):
    grant = GroupGrant.objects.filter(item_id=item_id, group_id=group_id).first()
    if grant is not None:
        grant.delete()
        logger.info(
            "group_grant_removed actor=%s item_id=%s group_id=%s",
            request.user.username,
            item_id,
            group_id,
        )
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_user_grants(request, item_id: int):
    item = get_object_or_404(VaultItem, pk=item_id)
    if item.is_deleted:
        return _deleted_error()
    serializer = UserIdsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user_ids = serializer.validated_data["user_ids"]

    users = list(User.objects.filter(pk__in=user_ids).order_by("username"))
    found_ids = {user.pk for user in users}
    missing = [user_id for user_id in user_ids if user_id not in found_ids]
    if missing:
        return Response(
            {
                "detail": "部分用户不存在。",
                "code": "unknown_users",
                "user_ids": missing,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    inactive = [user.pk for user in users if not user.is_active]
    if inactive:
        return Response(
            {
                "detail": "只能给启用中的用户授权。",
                "code": "inactive_users",
                "user_ids": inactive,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing = set(
        UserGrant.objects.filter(item=item, user_id__in=user_ids).values_list(
            "user_id", flat=True
        )
    )
    added: list[int] = []
    with transaction.atomic():
        for user in users:
            if user.pk in existing:
                continue
            UserGrant.objects.create(
                item=item, user=user, granted_by=request.user
            )
            added.append(user.pk)
            logger.info(
                "user_grant_added actor=%s item_id=%s target=%s",
                request.user.username,
                item.pk,
                user.username,
            )

    return Response(
        {
            "added": added,
            "already_granted": sorted(existing),
            "grant_count": item.user_grants.count(),
        },
        status=status.HTTP_201_CREATED if added else status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_user_grant_detail(request, item_id: int, user_id: int):
    grant = UserGrant.objects.filter(item_id=item_id, user_id=user_id).first()
    if grant is not None:
        grant.delete()
        logger.info(
            "user_grant_removed actor=%s item_id=%s target_id=%s",
            request.user.username,
            item_id,
            user_id,
        )
    return Response(status=status.HTTP_204_NO_CONTENT)

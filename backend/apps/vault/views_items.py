"""Endpoints for normal users to see items they were granted."""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .pagination import VaultPagination
from .serializers import MyItemSerializer
from .services import accessible_items


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_items(request):
    search = (request.query_params.get("q") or "").strip()[:50]
    queryset = accessible_items(request.user).select_related("owner").order_by(
        "-created_at", "-id"
    )
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(description__icontains=search)
        )

    paginator = VaultPagination()
    page = paginator.paginate_queryset(queryset, request, view=my_items)
    serializer = MyItemSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_item_detail(request, item_id: int):
    # Unauthorized users receive 404 rather than 403 so item IDs cannot be
    # used to discover whether an item exists.
    item = get_object_or_404(
        accessible_items(request.user).select_related("owner"), pk=item_id
    )
    return Response(MyItemSerializer(item).data)

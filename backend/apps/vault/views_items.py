"""Endpoints for normal users to see items they were granted."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .filters import apply_item_filters
from .pagination import VaultPagination
from .serializers import MyItemSerializer
from .services import accessible_items


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_items(request):
    queryset = accessible_items(request.user).select_related("owner").order_by(
        "-created_at", "-id"
    )
    queryset = apply_item_filters(queryset, request)

    paginator = VaultPagination()
    page = paginator.paginate_queryset(queryset, request, view=my_items)
    serializer = MyItemSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_dashboard(request):
    queryset = accessible_items(request.user)
    recent = queryset.select_related("owner").order_by(
        "-updated_at", "-id"
    )[:5]
    return Response(
        {
            "visible_items": queryset.count(),
            "recent_items": MyItemSerializer(recent, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_item_options(request):
    items = accessible_items(request.user).order_by()
    categories = sorted(
        {
            category
            for category in items.values_list("category", flat=True)
            if category
        }
    )
    tags = sorted(
        {
            tag
            for values in items.values_list("tags", flat=True)
            for tag in (values or [])
        }
    )
    return Response({"categories": categories, "tags": tags})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_item_detail(request, item_id: int):
    # Unauthorized users receive 404 rather than 403 so item IDs cannot be
    # used to discover whether an item exists.
    item = get_object_or_404(
        accessible_items(request.user).select_related("owner"), pk=item_id
    )
    return Response(MyItemSerializer(item).data)

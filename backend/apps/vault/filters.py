"""Shared item search and filter helpers for admin and user lists."""

from __future__ import annotations

from django.db.models import Q


def apply_item_filters(queryset, request):
    search = (request.query_params.get("q") or "").strip()[:50]
    category = (request.query_params.get("category") or "").strip()[:50]
    tag = (request.query_params.get("tag") or "").strip()[:30]

    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(category__icontains=search)
            | Q(tags_text__icontains=search)
        )
    if category:
        queryset = queryset.filter(category=category)
    if tag:
        # tags_text stores tags wrapped in an ASCII unit separator, so this
        # matches a whole tag without relying on SQLite JSON operators.
        queryset = queryset.filter(tags_text__icontains=f"\x1f{tag}\x1f")
    return queryset

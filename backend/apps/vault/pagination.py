"""Pagination shared by vault list endpoints."""

from rest_framework.pagination import PageNumberPagination


class VaultPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

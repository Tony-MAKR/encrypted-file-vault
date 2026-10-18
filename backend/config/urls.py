"""Root URL configuration."""

from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.core.urls")),
]

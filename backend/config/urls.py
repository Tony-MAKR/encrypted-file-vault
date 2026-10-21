"""Root URL configuration."""

from django.urls import include, path, re_path

from apps.core.views import spa_index

urlpatterns = [
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.vault.urls")),
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/", include("apps.audit.urls")),
    # React SPA fallback. API and Django static routes are never swallowed;
    # paths with a file extension are handled by spa_index with a 404.
    re_path(r"^(?!api(?:/|$)|static(?:/|$)).*$", spa_index, name="spa-index"),
]

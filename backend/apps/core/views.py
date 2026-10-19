"""Foundation endpoints. No business data is exposed in stage 1."""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_safe
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger("apps.core.health")


def _database_ok() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        return True
    except Exception as exc:
        # Do not expose connection strings or filesystem paths to the caller.
        logger.warning("数据库健康检查失败：%s", exc.__class__.__name__)
        return False


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Return a minimal liveness/readiness signal.

    This endpoint is intentionally public because it is used before login and
    by the local frontend. It must never include secrets, paths or user data.
    """

    database_ok = _database_ok()
    payload = {
        "status": "ok" if database_ok else "degraded",
        "database": "ok" if database_ok else "error",
        "version": settings.APP_VERSION,
    }
    http_status = status.HTTP_200_OK if database_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(payload, status=http_status)


@require_safe
def spa_index(request):
    """Serve the React entry point for client-side routes.

    WhiteNoise serves hashed assets and ``/index.html``. This view only handles
    page routes (``/``, ``/admin/items`` and so on). A missing file extension is
    treated as an application route; a path with an extension is a missing
    asset and must return 404 rather than a misleading HTML page.
    """

    index_path = Path(settings.FRONTEND_DIST_DIR) / "index.html"
    if not index_path.is_file():
        return HttpResponse(
            "网页资源尚未构建。请先在 frontend 目录运行 npm run build。",
            status=503,
            content_type="text/plain; charset=utf-8",
        )
    if Path(request.path).suffix:
        raise Http404

    response = FileResponse(
        index_path.open("rb"), content_type="text/html; charset=utf-8"
    )
    response["Cache-Control"] = "no-store"
    return response

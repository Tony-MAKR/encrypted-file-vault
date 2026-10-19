"""Health endpoint and HTTP security baseline tests."""

import pytest


@pytest.mark.django_db
def test_health_returns_ok(client):
    response = client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "version": "0.6.0",
    }
    assert response["Cache-Control"] == "no-store"
    assert response["X-Request-ID"]


@pytest.mark.django_db
def test_health_returns_503_when_database_is_unavailable(client, monkeypatch):
    monkeypatch.setattr("apps.core.views._database_ok", lambda: False)

    response = client.get("/api/v1/health/")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "database": "error",
        "version": "0.6.0",
    }


@pytest.mark.django_db
def test_security_headers_are_present(client):
    response = client.get("/api/v1/health/")

    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "same-origin"
    assert response["Permissions-Policy"].startswith("camera=()")
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"


@pytest.mark.django_db
def test_cors_allows_only_the_frontend_origin(client):
    allowed = client.get(
        "/api/v1/health/", HTTP_ORIGIN="http://127.0.0.1:5173"
    )
    blocked = client.get(
        "/api/v1/health/", HTTP_ORIGIN="http://untrusted.example"
    )

    assert allowed["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert "Access-Control-Allow-Origin" not in blocked


@pytest.mark.django_db
def test_health_sets_request_id_from_header(client):
    response = client.get(
        "/api/v1/health/", HTTP_X_REQUEST_ID="test-request-id"
    )

    assert response["X-Request-ID"] == "test-request-id"


def test_database_file_is_not_served_by_the_web_server(client):
    response = client.get("/data/db/db.sqlite3")

    assert response.status_code == 404


def test_log_rotation_is_configured():
    from django.conf import settings

    handler = settings.LOGGING["handlers"]["file"]

    assert handler["maxBytes"] == 10 * 1024 * 1024
    assert handler["backupCount"] == 5


def test_health_request_id_is_bounded(client, monkeypatch):
    # An oversized incoming ID must not be reflected as-is.
    monkeypatch.setattr("apps.core.views._database_ok", lambda: True)

    response = client.get(
        "/api/v1/health/", HTTP_X_REQUEST_ID="x" * 200
    )

    assert len(response["X-Request-ID"]) == 32
    assert set(response["X-Request-ID"]) <= set("0123456789abcdef")

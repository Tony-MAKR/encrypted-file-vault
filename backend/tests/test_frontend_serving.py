"""The backend serves the built React application for browser and desktop."""

from __future__ import annotations

import pytest

INDEX_MARKER = "<title>测试用前端</title>"


def body(response) -> str:
    if hasattr(response, "streaming_content"):
        return b"".join(response.streaming_content).decode("utf-8", errors="ignore")
    return response.content.decode("utf-8", errors="ignore")


@pytest.fixture
def frontend_dist(tmp_path, settings):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        f"<!doctype html><html><head>{INDEX_MARKER}</head>"
        '<body><div id="root"></div>'
        '<script type="module" src="/assets/app.js"></script></body></html>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('test');", encoding="utf-8")
    settings.FRONTEND_DIST_DIR = str(dist)
    return dist


@pytest.mark.django_db
def test_root_returns_the_frontend(client, frontend_dist):
    response = client.get("/")

    assert response.status_code == 200
    assert INDEX_MARKER in body(response)
    assert response["Content-Type"].startswith("text/html")
    assert response["Cache-Control"] == "no-store"
    assert "default-src 'self'" in response["Content-Security-Policy"]
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    ["/login", "/admin/items", "/admin/items/1", "/items/1", "/change-password"],
)
def test_react_routes_fall_back_to_index(client, frontend_dist, path):
    response = client.get(path)

    assert response.status_code == 200
    assert INDEX_MARKER in body(response)


@pytest.mark.django_db
def test_api_is_not_swallowed_by_the_spa_fallback(client, frontend_dist):
    health = client.get("/api/v1/health/")
    missing = client.get("/api/v1/does-not-exist/")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health["Content-Type"].startswith("application/json")
    assert missing.status_code == 404
    assert INDEX_MARKER not in body(missing)


@pytest.mark.django_db
def test_missing_asset_returns_404_not_index(client, frontend_dist):
    response = client.get("/assets/missing.js")

    assert response.status_code == 404
    assert INDEX_MARKER not in body(response)


@pytest.mark.django_db
def test_spa_index_only_accepts_read_methods(client, frontend_dist):
    response = client.post("/login")

    assert response.status_code == 405


@pytest.mark.django_db
def test_missing_build_returns_a_clear_error(client, settings, tmp_path):
    settings.FRONTEND_DIST_DIR = str(tmp_path / "not-built")

    response = client.get("/")

    assert response.status_code == 503
    assert "npm run build" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_database_file_cannot_be_reached_through_the_spa(client, frontend_dist):
    response = client.get("/data/db/db.sqlite3")

    assert response.status_code == 404

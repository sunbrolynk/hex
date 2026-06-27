"""Single-origin SPA serving."""

from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from hex.api.main import create_app
from hex.config import Settings


async def _get(app: FastAPI, path: str) -> Response:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.get(path)


async def test_spa_served_and_api_not_shadowed(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>HEx</title>SPA-OK")
    app = create_app(Settings(static_dir=str(tmp_path)))

    root = await _get(app, "/")
    assert root.status_code == 200
    assert "SPA-OK" in root.text

    health = await _get(app, "/health")  # API route still wins over the catch-all mount
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    openapi = await _get(app, "/openapi.json")  # API schema/docs not shadowed by the SPA mount
    assert openapi.status_code == 200


async def test_spa_history_fallback_serves_index_for_client_routes(tmp_path: Path) -> None:
    # A direct load of a client-side route (no matching file/route) must serve index.html so
    # React Router can render it — break-glass's /breakglass is only ever reached this way.
    (tmp_path / "index.html").write_text("<!doctype html><title>HEx</title>SPA-OK")
    app = create_app(Settings(static_dir=str(tmp_path)))

    deep = await _get(app, "/breakglass")
    assert deep.status_code == 200
    assert "SPA-OK" in deep.text

    # A real (guarded) API route still wins over the fallback — it 404s as JSON, not index.html.
    api = await _get(app, "/auth/breakglass")  # break-glass disabled here → guard 404
    assert api.status_code == 404
    assert "SPA-OK" not in api.text

    # A missing static asset stays a real 404 — the fallback is for navigation, not assets.
    asset = await _get(app, "/assets/missing.js")
    assert asset.status_code == 404
    assert "SPA-OK" not in asset.text


async def test_no_spa_mount_when_bundle_absent(tmp_path: Path) -> None:
    app = create_app(Settings(static_dir=str(tmp_path / "does-not-exist")))
    root = await _get(app, "/")
    assert root.status_code == 404  # nothing mounted; no SPA fallback
    health = await _get(app, "/health")
    assert health.status_code == 200

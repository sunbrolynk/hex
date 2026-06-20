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


async def test_no_spa_mount_when_bundle_absent(tmp_path: Path) -> None:
    app = create_app(Settings(static_dir=str(tmp_path / "does-not-exist")))
    root = await _get(app, "/")
    assert root.status_code == 404  # nothing mounted; no SPA fallback
    health = await _get(app, "/health")
    assert health.status_code == 200

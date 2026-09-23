import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret")
    from app.main import create_app

    return create_app()


def test_liveness(app) -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health/live")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_production_settings_require_gemini_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_readiness_reports_dependency_failure(app) -> None:
    from app.api.v1.health import get_readiness_checker

    async def unavailable():
        return {"database": True, "redis": False}

    app.dependency_overrides[get_readiness_checker] = lambda: unavailable

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health/ready")

    response = asyncio.run(request())

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert "password" not in response.text.lower()

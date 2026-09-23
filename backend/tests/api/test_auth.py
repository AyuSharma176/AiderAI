import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.models import Base


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-at-least-thirty-two-bytes")
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_login_and_me(client: httpx.AsyncClient) -> None:
    payload = {
        "email": " Person@Example.COM ",
        "name": "Person",
        "password": "Stronger123!",
    }
    registered = await client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    token = registered.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "person@example.com"

    logged_in = await client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "Stronger123!"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_duplicate_email_returns_stable_error(client: httpx.AsyncClient) -> None:
    payload = {
        "email": "person@example.com",
        "name": "Person",
        "password": "Stronger123!",
    }
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201

    duplicate = await client.post("/api/v1/auth/register", json=payload)

    assert duplicate.status_code == 409
    assert duplicate.json() | {"request_id": "ignored"} == {
        "code": "email_exists",
        "message": "An account with this email already exists",
        "request_id": "ignored",
    }


@pytest.mark.asyncio
async def test_invalid_token_paths_are_indistinguishable(client: httpx.AsyncClient) -> None:
    for token in ("not-a-token", "ey.invalid.forged"):
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json() | {"request_id": "ignored"} == {
            "code": "invalid_token",
            "message": "Invalid access token",
            "request_id": "ignored",
        }

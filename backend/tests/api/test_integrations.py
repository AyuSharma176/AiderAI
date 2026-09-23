from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_user
from app.api.v1.integrations import (
    get_gmail_dispatcher,
    get_google_oauth_client,
    get_oauth_state_store,
    get_token_cipher,
)
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.integrations.gmail.crypto import TokenCipher
from app.integrations.gmail.oauth import OAuthState
from app.integrations.gmail.types import GoogleOAuthTokens
from app.models import Base, CommerceOrder, EmailConnection, User


class FakeStateStore:
    async def issue(self, user_id, browser_nonce):
        self.user_id = user_id
        self.browser_nonce = browser_nonce
        return "valid-state"

    async def get_code_challenge(self, state):
        assert state == "valid-state"
        return "challenge"

    async def consume(self, state, browser_nonce):
        assert state == "valid-state"
        assert browser_nonce == self.browser_nonce
        return OAuthState(
            user_id=self.user_id,
            browser_nonce_hash="unused",
            code_verifier="verifier",
        )


class FakeOAuthClient:
    def authorization_url(self, state, challenge):
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}&c={challenge}"

    async def exchange_code(self, code, verifier):
        assert (code, verifier) == ("valid-code", "verifier")
        return GoogleOAuthTokens(
            access_token="access-secret",
            refresh_token="refresh-secret",
            expires_in=3600,
            scope="https://www.googleapis.com/auth/gmail.readonly",
        )

    async def get_profile(self, access_token):
        assert access_token == "access-secret"
        return {"emailAddress": "orders@example.com", "historyId": "10"}

    async def revoke(self, token):
        self.revoked = token


@pytest.fixture
async def integration_context(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    from app.main import create_app

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user = User(email="orders@example.com", name="Orders", password_hash="hash")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    state_store = FakeStateStore()
    oauth = FakeOAuthClient()
    cipher = TokenCipher([Fernet.generate_key().decode()])
    queued: list[tuple[str, str]] = []
    settings = Settings(
        APP_ENV="test",
        JWT_SECRET="test-secret",
        GMAIL_INTEGRATION_ENABLED=True,
        GOOGLE_OAUTH_CLIENT_ID="client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="client-secret",
        GMAIL_TOKEN_ENCRYPTION_KEYS=[Fernet.generate_key().decode()],
        _env_file=None,
    )
    app = create_app()

    async def db_override():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_oauth_state_store] = lambda: state_store
    app.dependency_overrides[get_google_oauth_client] = lambda: oauth
    app.dependency_overrides[get_token_cipher] = lambda: cipher
    app.dependency_overrides[get_gmail_dispatcher] = lambda: (
        lambda connection_id, mode: queued.append((connection_id, mode))
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as client:
        yield SimpleNamespace(
            client=client,
            sessions=sessions,
            user=user,
            state_store=state_store,
            oauth=oauth,
            cipher=cipher,
            queued=queued,
            app=app,
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_authorize_returns_google_url_without_tokens(integration_context) -> None:
    response = await integration_context.client.post("/api/v1/integrations/gmail/authorize")

    assert response.status_code == 200
    assert response.json()["authorization_url"].startswith("https://accounts.google.com/")
    assert "token" not in response.text.lower()
    assert response.cookies.get("gmail_oauth_nonce")


@pytest.mark.asyncio
async def test_callback_persists_encrypted_refresh_token_and_queues_sync(
    integration_context,
) -> None:
    await integration_context.client.post("/api/v1/integrations/gmail/authorize")

    response = await integration_context.client.get(
        "/api/v1/integrations/gmail/callback?code=valid-code&state=valid-state"
    )

    assert response.status_code == 303
    async with integration_context.sessions() as session:
        connection = await session.scalar(select(EmailConnection))
        assert connection is not None
        assert connection.encrypted_refresh_token != "refresh-secret"
        assert integration_context.cipher.decrypt(connection.encrypted_refresh_token) == (
            "refresh-secret"
        )
    assert integration_context.queued == [(str(connection.id), "full")]


@pytest.mark.asyncio
async def test_status_and_delete_imported_orders_are_user_scoped(integration_context) -> None:
    response = await integration_context.client.get("/api/v1/integrations/gmail")
    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"

    response = await integration_context.client.delete("/api/v1/integrations/gmail/orders")
    assert response.status_code == 204
    async with integration_context.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(CommerceOrder)) == 0


@pytest.mark.asyncio
async def test_disconnect_revokes_token_then_is_idempotent(integration_context) -> None:
    await integration_context.client.post("/api/v1/integrations/gmail/authorize")
    await integration_context.client.get(
        "/api/v1/integrations/gmail/callback?code=valid-code&state=valid-state"
    )

    first = await integration_context.client.delete("/api/v1/integrations/gmail")
    second = await integration_context.client.delete("/api/v1/integrations/gmail")

    assert first.status_code == second.status_code == 204
    assert integration_context.oauth.revoked == "refresh-secret"
    async with integration_context.sessions() as session:
        connection = await session.scalar(select(EmailConnection))
        assert connection is not None
        assert connection.status.value == "disconnected"
        assert connection.encrypted_refresh_token == ""


@pytest.mark.asyncio
async def test_disabled_feature_is_not_exposed(integration_context) -> None:
    disabled = Settings(APP_ENV="test", JWT_SECRET="test-secret", _env_file=None)
    integration_context.app.dependency_overrides[get_settings] = lambda: disabled

    response = await integration_context.client.get("/api/v1/integrations/gmail")

    assert response.status_code == 404

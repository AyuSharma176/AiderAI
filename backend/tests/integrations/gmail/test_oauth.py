from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest

from app.integrations.gmail.oauth import (
    GoogleOAuthClient,
    InvalidOAuthState,
    OAuthConsentDenied,
    OAuthProviderUnavailable,
    OAuthStateStore,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int) -> None:
        del ex
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def eval(self, script: str, numkeys: int, key: str) -> str | None:
        del script, numkeys
        return self.values.pop(key, None)


@pytest.mark.asyncio
async def test_state_is_single_use_bound_to_user_and_browser() -> None:
    user_id = uuid4()
    store = OAuthStateStore(FakeRedis(), ttl_seconds=600)
    state = await store.issue(user_id, "browser-a")

    consumed = await store.consume(state, "browser-a")

    assert consumed.user_id == user_id
    with pytest.raises(InvalidOAuthState):
        await store.consume(state, "browser-a")


@pytest.mark.asyncio
async def test_state_rejects_a_different_browser() -> None:
    store = OAuthStateStore(FakeRedis(), ttl_seconds=600)
    state = await store.issue(uuid4(), "browser-a")

    with pytest.raises(InvalidOAuthState):
        await store.consume(state, "browser-b")


@pytest.mark.asyncio
async def test_state_exposes_pkce_challenge_without_exposing_verifier() -> None:
    store = OAuthStateStore(FakeRedis(), ttl_seconds=600)
    state = await store.issue(uuid4(), "browser-a")

    challenge = await store.get_code_challenge(state)

    assert challenge
    assert challenge != state


def make_client(handler: httpx.MockTransport) -> GoogleOAuthClient:
    return GoogleOAuthClient(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://support.example/api/v1/integrations/gmail/callback",
        http_client=httpx.AsyncClient(transport=handler),
    )


def test_authorization_url_has_exact_readonly_scope_and_pkce() -> None:
    client = make_client(httpx.MockTransport(lambda request: httpx.Response(200)))

    url = client.authorization_url("state-1", "challenge-1")
    query = parse_qs(urlsplit(url).query)

    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert query["access_type"] == ["offline"]
    assert query["state"] == ["state-1"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["prompt"] == ["consent"]


@pytest.mark.asyncio
async def test_exchange_maps_provider_failure_without_leaking_payload() -> None:
    secret_payload = "provider-secret-details"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=secret_payload, request=request)

    client = make_client(httpx.MockTransport(handler))

    with pytest.raises(OAuthProviderUnavailable) as exc_info:
        await client.exchange_code("code", "verifier")
    assert secret_payload not in str(exc_info.value)


@pytest.mark.asyncio
async def test_exchange_allows_missing_refresh_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "access",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
                "token_type": "Bearer",
            },
            request=request,
        )

    tokens = await make_client(httpx.MockTransport(handler)).exchange_code("code", "verifier")

    assert tokens.refresh_token is None
    assert tokens.access_token == "access"


def test_denied_consent_is_mapped_without_provider_text() -> None:
    client = make_client(httpx.MockTransport(lambda request: httpx.Response(200)))

    with pytest.raises(OAuthConsentDenied, match="declined"):
        client.raise_for_callback_error("access_denied", "private provider message")

import base64
import secrets
from hashlib import sha256
from hmac import compare_digest
from typing import Protocol
from urllib.parse import urlencode
from uuid import UUID

import httpx
from pydantic import BaseModel

from app.integrations.gmail.types import GoogleOAuthTokens

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
GET_AND_DELETE_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if value then redis.call('DEL', KEYS[1]) end
return value
"""


class OAuthRedis(Protocol):
    async def set(self, key: str, value: str, *, ex: int) -> object: ...
    async def get(self, key: str) -> str | bytes | None: ...
    async def eval(self, script: str, numkeys: int, key: str) -> str | bytes | None: ...


class OAuthState(BaseModel):
    user_id: UUID
    browser_nonce_hash: str
    code_verifier: str


class InvalidOAuthState(RuntimeError):
    pass


class OAuthConsentDenied(RuntimeError):
    pass


class OAuthProviderUnavailable(RuntimeError):
    pass


class OAuthStateStore:
    def __init__(self, redis: OAuthRedis, *, ttl_seconds: int = 600) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _digest(value: str) -> str:
        return sha256(value.encode()).hexdigest()

    @staticmethod
    def _key(state: str) -> str:
        return f"oauth:gmail:{sha256(state.encode()).hexdigest()}"

    @staticmethod
    def _challenge(verifier: str) -> str:
        return base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    async def issue(self, user_id: UUID, browser_nonce: str) -> str:
        state = secrets.token_urlsafe(32)
        payload = OAuthState(
            user_id=user_id,
            browser_nonce_hash=self._digest(browser_nonce),
            code_verifier=secrets.token_urlsafe(64),
        )
        await self.redis.set(self._key(state), payload.model_dump_json(), ex=self.ttl_seconds)
        return state

    async def get_code_challenge(self, state: str) -> str:
        payload = await self.redis.get(self._key(state))
        if payload is None:
            raise InvalidOAuthState("Authorization state is invalid or expired")
        parsed = OAuthState.model_validate_json(payload)
        return self._challenge(parsed.code_verifier)

    async def consume(self, state: str, browser_nonce: str) -> OAuthState:
        payload = await self.redis.eval(GET_AND_DELETE_SCRIPT, 1, self._key(state))
        if payload is None:
            raise InvalidOAuthState("Authorization state is invalid or expired")
        parsed = OAuthState.model_validate_json(payload)
        if not compare_digest(parsed.browser_nonce_hash, self._digest(browser_nonce)):
            raise InvalidOAuthState("Authorization state is invalid or expired")
        return parsed


class GoogleOAuthClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.http_client = http_client

    def authorization_url(self, state: str, code_challenge: str) -> str:
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": GMAIL_READONLY_SCOPE,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "false",
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{AUTHORIZATION_ENDPOINT}?{query}"

    def raise_for_callback_error(self, error: str | None, description: str | None = None) -> None:
        del description
        if error == "access_denied":
            raise OAuthConsentDenied("Google authorization was declined")
        if error:
            raise OAuthProviderUnavailable("Google authorization is temporarily unavailable")

    async def exchange_code(self, code: str, code_verifier: str) -> GoogleOAuthTokens:
        try:
            response = await self.http_client.post(
                TOKEN_ENDPOINT,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "code_verifier": code_verifier,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            return GoogleOAuthTokens.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthProviderUnavailable(
                "Google authorization is temporarily unavailable"
            ) from exc

    async def revoke(self, token: str) -> None:
        try:
            response = await self.http_client.post(
                REVOKE_ENDPOINT,
                data={"token": token},
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OAuthProviderUnavailable(
                "Google authorization is temporarily unavailable"
            ) from exc

import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx

from app.integrations.gmail.types import GmailHistoryPage, GmailMessagePage, GmailRawMessage

GMAIL_API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailUnavailableError(RuntimeError):
    pass


class GmailAuthenticationError(RuntimeError):
    pass


class GmailHistoryExpired(RuntimeError):
    pass


class GmailRateLimited(RuntimeError):
    pass


class GmailClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        access_token_provider: Callable[[], str | Awaitable[str]],
        api_root: str = GMAIL_API_ROOT,
    ) -> None:
        self.http_client = http_client
        self.access_token_provider = access_token_provider
        self.api_root = api_root.rstrip("/")
        self._access_token: str | None = None

    async def _token(self) -> str:
        if self._access_token is not None:
            return self._access_token
        value = self.access_token_provider()
        self._access_token = await value if inspect.isawaitable(value) else value
        return self._access_token

    async def _get(
        self, path: str, *, params: dict[str, str], history_request: bool = False
    ) -> httpx.Response:
        token = await self._token()
        try:
            response = await self.http_client.get(
                f"{self.api_root}/{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=httpx.Timeout(15.0, connect=5.0),
            )
        except httpx.HTTPError as exc:
            raise GmailUnavailableError("Gmail is temporarily unavailable") from exc
        if response.status_code == 401:
            raise GmailAuthenticationError("Gmail authorization must be renewed")
        if history_request and response.status_code == 404:
            raise GmailHistoryExpired("Gmail history cursor has expired")
        if response.status_code == 429:
            raise GmailRateLimited("Gmail request limit reached")
        if response.status_code >= 400:
            raise GmailUnavailableError("Gmail is temporarily unavailable")
        return response

    async def list_candidate_ids(
        self, after: datetime, page_token: str | None
    ) -> GmailMessagePage:
        params = {
            "q": (
                f"after:{after:%Y/%m/%d} "
                "(from:amazon.in OR from:flipkart.com)"
            ),
            "maxResults": "100",
        }
        if page_token:
            params["pageToken"] = page_token
        response = await self._get("messages", params=params)
        return GmailMessagePage.model_validate(response.json())

    async def get_message(self, message_id: str) -> GmailRawMessage:
        response = await self._get(
            f"messages/{message_id}", params={"format": "full"}
        )
        return GmailRawMessage.model_validate(response.json())

    async def list_history(
        self, start_history_id: str, page_token: str | None
    ) -> GmailHistoryPage:
        params = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "maxResults": "100",
        }
        if page_token:
            params["pageToken"] = page_token
        response = await self._get("history", params=params, history_request=True)
        return GmailHistoryPage.model_validate(response.json())

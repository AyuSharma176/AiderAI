from datetime import UTC, datetime

import httpx
import pytest

from app.integrations.gmail.client import GmailClient, GmailUnavailableError


@pytest.mark.asyncio
async def test_candidate_query_is_bounded_to_senders_and_date() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"messages": [], "historyId": "10"})

    client = GmailClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        access_token_provider=lambda: "access-token",
    )

    await client.list_candidate_ids(datetime(2025, 9, 24, tzinfo=UTC), None)

    query = requests[0].url.params
    assert "after:2025/09/24" in query["q"]
    assert "from:amazon.in OR from:flipkart.com" in query["q"]
    assert query["maxResults"] == "100"
    assert requests[0].headers["authorization"] == "Bearer access-token"


@pytest.mark.asyncio
async def test_provider_payload_is_not_leaked_on_failure() -> None:
    secret = "user@example.com token=secret"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": secret}}, request=request)

    client = GmailClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        access_token_provider=lambda: "access-token",
    )

    with pytest.raises(GmailUnavailableError, match="temporarily unavailable") as caught:
        await client.get_message("m1")
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_history_request_uses_cursor_and_page_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"history": [], "historyId": "12"})

    client = GmailClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        access_token_provider=lambda: "access-token",
    )

    page = await client.list_history("10", "next")

    assert requests[0].url.params["startHistoryId"] == "10"
    assert requests[0].url.params["pageToken"] == "next"
    assert page.history_id == "12"

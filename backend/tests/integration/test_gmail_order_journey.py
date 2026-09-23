import asyncio
import os
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("INTEGRATION_API_URL"),
    reason="Compose Gmail integration environment is not active",
)


@pytest.mark.asyncio
async def test_gmail_orders_flow() -> None:
    async with httpx.AsyncClient(
        base_url=os.environ["INTEGRATION_API_URL"], timeout=15
    ) as client:
        email = f"orders-{uuid4()}@example.com"
        registered = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "name": "Orders", "password": "SecurePass123!"},
        )
        registered.raise_for_status()
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        authorization = await client.post(
            "/api/v1/integrations/gmail/authorize", headers=headers
        )
        authorization.raise_for_status()
        consent = await client.get(authorization.json()["authorization_url"])
        assert consent.status_code in {302, 307}
        callback = await client.get(consent.headers["location"])
        assert callback.status_code == 303

        for _ in range(30):
            orders = await client.get("/api/v1/orders", headers=headers)
            orders.raise_for_status()
            if len(orders.json()["items"]) == 2:
                break
            await asyncio.sleep(1)
        else:
            pytest.fail("Gmail order synchronization did not complete")

        assert {
            (item["marketplace"], item["marketplace_order_id"])
            for item in orders.json()["items"]
        } == {
            ("amazon", "402-0000000-0000000"),
            ("flipkart", "OD000000000000000000"),
        }

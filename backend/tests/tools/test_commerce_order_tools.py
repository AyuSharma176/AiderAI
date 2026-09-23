from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import (
    Base,
    CommerceOrder,
    CommerceOrderItem,
    CommerceOrderStatus,
    EmailConnection,
    EmailConnectionStatus,
    Marketplace,
    User,
)
from app.tools.registry import execute_tool


@pytest.fixture
async def context():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user_a = User(email="a@example.com", name="A", password_hash="hash")
        user_b = User(email="b@example.com", name="B", password_hash="hash")
        session.add_all([user_a, user_b])
        await session.flush()
        order_a = CommerceOrder(
            user_id=user_a.id,
            marketplace=Marketplace.AMAZON,
            marketplace_order_id="A-1",
            status=CommerceOrderStatus.SHIPPED,
            placed_at=datetime(2026, 9, 20, tzinfo=UTC),
        )
        order_b = CommerceOrder(
            user_id=user_b.id,
            marketplace=Marketplace.FLIPKART,
            marketplace_order_id="F-2",
            status=CommerceOrderStatus.DELIVERED,
        )
        connection = EmailConnection(
            user_id=user_a.id,
            provider="gmail",
            provider_account_id="a@example.com",
            email_address="a@example.com",
            encrypted_refresh_token="v1:opaque",
            granted_scopes="gmail.readonly",
            status=EmailConnectionStatus.CONNECTED,
            last_sync_completed_at=datetime(2026, 9, 24, tzinfo=UTC),
        )
        session.add_all([order_a, order_b, connection])
        await session.flush()
        session.add(
            CommerceOrderItem(order_id=order_a.id, title="USB-C charger", quantity=1)
        )
        await session.commit()
        yield session, user_a, user_b, order_a, order_b
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_my_order_ignores_model_identity_and_scopes_owner(context) -> None:
    session, user_a, user_b, _, user_b_order = context

    result = await execute_tool(
        "get_my_order",
        {"order_id": str(user_b_order.id), "user_id": str(user_b.id)},
        user_a.id,
        session,
    )

    assert result.data["found"] is False


@pytest.mark.asyncio
async def test_list_my_orders_returns_freshness_without_source_email(context) -> None:
    session, user_a, _, _, _ = context

    result = await execute_tool("list_my_orders", {"limit": 10}, user_a.id, session)

    assert result.data["last_synced_at"] is not None
    assert result.data["orders"][0]["marketplace_order_id"] == "A-1"
    assert "email_body" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_find_my_orders_by_product_is_owner_scoped(context) -> None:
    session, user_a, _, _, _ = context

    result = await execute_tool(
        "find_my_orders_by_product", {"query": "charger", "limit": 5}, user_a.id, session
    )

    assert [order["marketplace_order_id"] for order in result.data["orders"]] == ["A-1"]

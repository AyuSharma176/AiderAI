from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models import (
    Base,
    CommerceOrder,
    CommerceOrderItem,
    CommerceOrderStatus,
    Marketplace,
    User,
)


@pytest.fixture
async def order_context(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    from app.main import create_app

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
            marketplace_url="https://www.amazon.in/order/A-1",
        )
        order_b = CommerceOrder(
            user_id=user_b.id,
            marketplace=Marketplace.AMAZON,
            marketplace_order_id="A-1",
            status=CommerceOrderStatus.SHIPPED,
            placed_at=datetime(2026, 9, 21, tzinfo=UTC),
            marketplace_url="https://evil.example/phish",
        )
        session.add_all([order_a, order_b])
        await session.flush()
        session.add(
            CommerceOrderItem(order_id=order_a.id, title="USB-C charger", quantity=1)
        )
        await session.commit()

    app = create_app()

    async def db_override():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: user_a
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield SimpleNamespace(client=client, user_a=user_a, user_b_order=order_b, app=app)
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_filters_by_owner_marketplace_status_and_query(order_context) -> None:
    response = await order_context.client.get(
        "/api/v1/orders?marketplace=amazon&status=shipped&q=charger"
    )

    assert response.status_code == 200
    assert [item["marketplace_order_id"] for item in response.json()["items"]] == ["A-1"]
    assert response.json()["items"][0]["items"][0]["title"] == "USB-C charger"

    too_recent = await order_context.client.get(
        "/api/v1/orders?since=2026-09-21T00:00:00Z"
    )
    assert too_recent.status_code == 200
    assert too_recent.json()["items"] == []


@pytest.mark.asyncio
async def test_foreign_order_id_is_not_found(order_context) -> None:
    response = await order_context.client.get(
        f"/api/v1/orders/{order_context.user_b_order.id}"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_cursor_is_rejected(order_context) -> None:
    response = await order_context.client.get("/api/v1/orders?cursor=not-valid")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_detail_emits_only_validated_marketplace_url(order_context) -> None:
    order_context.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=order_context.user_b_order.user_id
    )

    response = await order_context.client.get(
        f"/api/v1/orders/{order_context.user_b_order.id}"
    )

    assert response.status_code == 200
    assert response.json()["marketplace_url"] is None
    assert "last_sync_completed_at" in response.json()

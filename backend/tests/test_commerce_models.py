from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, User
from app.models.commerce_order import (
    CommerceOrder,
    CommerceOrderStatus,
    Marketplace,
    OrderEventType,
    OrderSourceEvent,
)
from app.models.email_connection import EmailConnection, EmailConnectionStatus


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


async def create_user(session, email: str) -> User:
    user = User(email=email, name=email, password_hash="hash")
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_same_marketplace_order_is_unique_per_user(session) -> None:
    user_a = await create_user(session, "a@example.com")
    user_b = await create_user(session, "b@example.com")
    session.add_all(
        [
            CommerceOrder(
                user_id=user_a.id,
                marketplace=Marketplace.AMAZON,
                marketplace_order_id="A-1",
                status=CommerceOrderStatus.PLACED,
            ),
            CommerceOrder(
                user_id=user_b.id,
                marketplace=Marketplace.AMAZON,
                marketplace_order_id="A-1",
                status=CommerceOrderStatus.PLACED,
            ),
        ]
    )

    await session.commit()


@pytest.mark.asyncio
async def test_duplicate_marketplace_order_for_one_user_is_rejected(session) -> None:
    user = await create_user(session, "a@example.com")
    values = {
        "user_id": user.id,
        "marketplace": Marketplace.AMAZON,
        "marketplace_order_id": "A-1",
        "status": CommerceOrderStatus.PLACED,
    }
    session.add_all([CommerceOrder(**values), CommerceOrder(**values)])

    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_duplicate_source_message_for_connection_is_rejected(session) -> None:
    user = await create_user(session, "a@example.com")
    connection = EmailConnection(
        user_id=user.id,
        provider="gmail",
        provider_account_id="acct-1",
        email_address="a@example.com",
        encrypted_refresh_token="v1:encrypted",
        granted_scopes="https://www.googleapis.com/auth/gmail.readonly",
        status=EmailConnectionStatus.CONNECTED,
    )
    order = CommerceOrder(
        user_id=user.id,
        marketplace=Marketplace.FLIPKART,
        marketplace_order_id="F-1",
        status=CommerceOrderStatus.SHIPPED,
    )
    session.add_all([connection, order])
    await session.flush()
    event_values = {
        "order_id": order.id,
        "connection_id": connection.id,
        "provider_message_id_hash": "opaque-hash",
        "event_type": OrderEventType.SHIPPED,
        "event_at": datetime.now(UTC),
        "parser_name": "flipkart",
        "parser_version": "1",
        "facts": {"carrier": "Ekart"},
    }
    session.add_all([OrderSourceEvent(**event_values), OrderSourceEvent(**event_values)])

    with pytest.raises(IntegrityError):
        await session.commit()

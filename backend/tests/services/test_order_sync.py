import asyncio
import base64
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.integrations.gmail.client import GmailAuthenticationError, GmailHistoryExpired
from app.integrations.gmail.crypto import TokenCipher
from app.integrations.gmail.types import GmailHistoryPage, GmailMessagePage, GmailRawMessage
from app.models import Base, CommerceOrder, EmailConnection, OrderSourceEvent, User
from app.models.email_connection import EmailConnectionStatus
from app.orders.parsers import PARSER_REGISTRY
from app.services.order_sync import InMemorySyncLock, OrderSynchronizer


def encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def amazon_message() -> GmailRawMessage:
    return GmailRawMessage.model_validate(
        {
            "id": "m1",
            "historyId": "11",
            "internalDate": "1789898400000",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "updates@amazon.in"},
                    {"name": "Subject", "value": "Confirmed 402-0000000-0000000"},
                ],
                "body": {
                    "data": encoded(
                        "Order confirmed. Order # 402-0000000-0000000 "
                        "Item: USB-C charger (Qty: 1)"
                    )
                },
            },
        }
    )


class FakeGmail:
    def __init__(self) -> None:
        self.history_error: Exception | None = None
        self.full_query_after: datetime | None = None
        self.message_ids = ["m1"]
        self.fail_on_message: str | None = None

    async def list_candidate_ids(self, after: datetime, page_token: str | None):
        self.full_query_after = after
        await asyncio.sleep(0)
        return GmailMessagePage(
            messages=[{"id": message_id} for message_id in self.message_ids],
            historyId="11",
        )

    async def get_message(self, message_id: str):
        if message_id == self.fail_on_message:
            raise RuntimeError("provider failed")
        await asyncio.sleep(0.01)
        return amazon_message()

    async def list_history(self, start_history_id: str, page_token: str | None):
        if self.history_error:
            raise self.history_error
        return GmailHistoryPage(history=[], historyId="11")


@pytest.fixture
async def sync_context():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    key = Fernet.generate_key().decode()
    cipher = TokenCipher([key])
    async with sessions() as session:
        user = User(email="orders@example.com", name="Orders", password_hash="hash")
        session.add(user)
        await session.flush()
        connection = EmailConnection(
            user_id=user.id,
            provider="gmail",
            provider_account_id="gmail-1",
            email_address=user.email,
            encrypted_refresh_token=cipher.encrypt("refresh-token"),
            granted_scopes="https://www.googleapis.com/auth/gmail.readonly",
            status=EmailConnectionStatus.CONNECTED,
        )
        session.add(connection)
        await session.commit()

    gmail = FakeGmail()
    synchronizer = OrderSynchronizer(
        sessions,
        gmail,
        PARSER_REGISTRY,
        cipher,
        Settings(JWT_SECRET="test-secret", APP_ENV="test", _env_file=None),
        InMemorySyncLock(),
        message_id_pepper="test-pepper",
        now=lambda: datetime(2026, 9, 24, tzinfo=UTC),
    )
    yield sessions, user, connection, gmail, synchronizer
    await engine.dispose()


@pytest.mark.asyncio
async def test_initial_sync_upserts_order_and_discards_raw_body(sync_context) -> None:
    sessions, user, connection, _, synchronizer = sync_context

    result = await synchronizer.sync(connection.id, mode="full")

    async with sessions() as session:
        order = await session.scalar(
            select(CommerceOrder).where(
                CommerceOrder.marketplace_order_id == "402-0000000-0000000"
            )
        )
        assert order is not None
        assert order.user_id == user.id
        assert order.placed_at.replace(tzinfo=UTC) == datetime.fromtimestamp(
            1789898400, tz=UTC
        )
        assert not hasattr(order, "raw_email")
    assert result.order_count == 1


@pytest.mark.asyncio
async def test_repeated_message_and_overlapping_sync_do_not_duplicate(sync_context) -> None:
    sessions, _, connection, _, synchronizer = sync_context

    first, second = await asyncio.gather(
        synchronizer.sync(connection.id, mode="full"),
        synchronizer.sync(connection.id, mode="full"),
    )

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(CommerceOrder)) == 1
        assert await session.scalar(select(func.count()).select_from(OrderSourceEvent)) == 1
    assert {first.skipped_locked, second.skipped_locked} == {False, True}


@pytest.mark.asyncio
async def test_expired_history_cursor_runs_bounded_reconciliation(sync_context) -> None:
    _, _, connection, gmail, synchronizer = sync_context
    connection.last_history_id = "old"
    async with synchronizer.session_factory() as session:
        await session.merge(connection)
        await session.commit()
    gmail.history_error = GmailHistoryExpired()

    await synchronizer.sync(connection.id)

    assert gmail.full_query_after == datetime(2025, 9, 24, tzinfo=UTC)


@pytest.mark.asyncio
async def test_connection_owner_controls_all_written_orders(sync_context) -> None:
    sessions, user, connection, _, synchronizer = sync_context

    await synchronizer.sync(connection.id, mode="full")

    async with sessions() as session:
        assert set(await session.scalars(select(CommerceOrder.user_id))) == {user.id}


@pytest.mark.asyncio
async def test_invalid_grant_marks_connection_for_reconnect(sync_context) -> None:
    sessions, _, connection, gmail, synchronizer = sync_context
    connection.last_history_id = "old"
    async with sessions() as session:
        await session.merge(connection)
        await session.commit()
    gmail.history_error = GmailAuthenticationError("expired")

    with pytest.raises(GmailAuthenticationError):
        await synchronizer.sync(connection.id)

    async with sessions() as session:
        persisted = await session.get(EmailConnection, connection.id)
        assert persisted is not None
        assert persisted.status == EmailConnectionStatus.RECONNECT_REQUIRED
        assert persisted.last_sync_error_code == "invalid_grant"
        assert persisted.last_sync_completed_at is None


@pytest.mark.asyncio
async def test_partial_batch_failure_rolls_back_orders_and_restores_connected_status(
    sync_context,
) -> None:
    sessions, _, connection, gmail, synchronizer = sync_context
    gmail.message_ids = ["m1", "m2"]
    gmail.fail_on_message = "m2"

    with pytest.raises(RuntimeError, match="provider failed"):
        await synchronizer.sync(connection.id, mode="full")

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(CommerceOrder)) == 0
        persisted = await session.get(EmailConnection, connection.id)
        assert persisted is not None
        assert persisted.status == EmailConnectionStatus.CONNECTED
        assert persisted.last_sync_error_code == "sync_failed"
        assert persisted.last_sync_completed_at is None

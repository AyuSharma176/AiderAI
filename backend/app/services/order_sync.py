from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.integrations.gmail.client import GmailAuthenticationError, GmailHistoryExpired
from app.integrations.gmail.crypto import TokenCipher
from app.models import (
    CommerceOrder,
    CommerceOrderItem,
    CommerceOrderStatus,
    EmailConnection,
    EmailConnectionStatus,
    OrderEventType,
    OrderSourceEvent,
)
from app.models.base import utc_now
from app.orders.parsers.base import OrderEmailParser, normalize_message
from app.orders.types import OrderObservation


class SyncLock(Protocol):
    async def acquire(self, connection_id: UUID) -> bool: ...
    async def release(self, connection_id: UUID) -> None: ...


class InMemorySyncLock:
    def __init__(self) -> None:
        self._held: set[UUID] = set()

    async def acquire(self, connection_id: UUID) -> bool:
        if connection_id in self._held:
            return False
        self._held.add(connection_id)
        return True

    async def release(self, connection_id: UUID) -> None:
        self._held.discard(connection_id)


class PostgreSQLSyncLock:
    """Hold a session-level advisory lock for the complete synchronization."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self._connections: dict[UUID, AsyncConnection] = {}

    @staticmethod
    def _key(connection_id: UUID) -> int:
        value = int.from_bytes(connection_id.bytes[:8], signed=False)
        return value if value < 2**63 else value - 2**64

    async def acquire(self, connection_id: UUID) -> bool:
        connection = await self.engine.connect()
        acquired = bool(
            await connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": self._key(connection_id)}
            )
        )
        if not acquired:
            await connection.close()
            return False
        self._connections[connection_id] = connection
        return True

    async def release(self, connection_id: UUID) -> None:
        connection = self._connections.pop(connection_id, None)
        if connection is not None:
            await connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": self._key(connection_id)}
            )
            await connection.close()


@dataclass(frozen=True)
class SyncResult:
    candidate_count: int = 0
    parsed_count: int = 0
    skipped_count: int = 0
    order_count: int = 0
    history_id: str = ""
    skipped_locked: bool = False


_STATUS_PRECEDENCE = {
    CommerceOrderStatus.UNKNOWN: 0,
    CommerceOrderStatus.PLACED: 1,
    CommerceOrderStatus.SHIPPED: 2,
    CommerceOrderStatus.OUT_FOR_DELIVERY: 3,
    CommerceOrderStatus.DELIVERED: 4,
    CommerceOrderStatus.RETURN_UPDATE: 5,
    CommerceOrderStatus.CANCELLED: 6,
}
_MESSAGE_FETCH_CONCURRENCY = 8


def _subtract_months(value: datetime, months: int) -> datetime:
    absolute = value.year * 12 + value.month - 1 - months
    year, month_index = divmod(absolute, 12)
    month = month_index + 1
    days = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return value.replace(year=year, month=month, day=min(value.day, days[month - 1]))


class OrderSynchronizer:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gmail,
        parsers: Sequence[OrderEmailParser],
        token_cipher: TokenCipher,
        settings: Settings,
        lock: SyncLock,
        *,
        message_id_pepper: str,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session_factory = session_factory
        self.gmail = gmail
        self.parsers = parsers
        self.token_cipher = token_cipher
        self.settings = settings
        self.lock = lock
        self.message_id_pepper = message_id_pepper
        self.now = now

    async def sync(
        self, connection_id: UUID, mode: Literal["auto", "full"] = "auto"
    ) -> SyncResult:
        if not await self.lock.acquire(connection_id):
            return SyncResult(skipped_locked=True)
        try:
            async with self.session_factory() as session:
                connection = await session.get(EmailConnection, connection_id)
                if connection is None or connection.status == EmailConnectionStatus.DISCONNECTED:
                    return SyncResult()
                self.token_cipher.decrypt(connection.encrypted_refresh_token)
                connection.status = EmailConnectionStatus.SYNCING
                connection.last_sync_started_at = self.now()
                connection.last_sync_error_code = None
                await session.commit()

            try:
                ids, history_id = await self._candidate_ids(connection, mode)
                result = await self._persist_messages(connection, ids, history_id)
            except GmailAuthenticationError:
                await self._finish(connection_id, EmailConnectionStatus.RECONNECT_REQUIRED, "invalid_grant")
                raise
            except Exception:
                await self._finish(connection_id, EmailConnectionStatus.CONNECTED, "sync_failed")
                raise
            await self._finish(connection_id, EmailConnectionStatus.CONNECTED, None, history_id)
            return result
        finally:
            await self.lock.release(connection_id)

    async def _candidate_ids(
        self, connection: EmailConnection, mode: Literal["auto", "full"]
    ) -> tuple[list[str], str]:
        if mode == "full" or not connection.last_history_id:
            return await self._full_ids()
        try:
            ids: list[str] = []
            page_token: str | None = None
            history_id = connection.last_history_id
            while True:
                page = await self.gmail.list_history(connection.last_history_id, page_token)
                ids.extend(
                    added.message.id
                    for record in page.history
                    for added in record.messages_added
                )
                history_id = page.history_id
                page_token = page.next_page_token
                if not page_token:
                    return list(dict.fromkeys(ids)), history_id
        except GmailHistoryExpired:
            return await self._full_ids()

    async def _full_ids(self) -> tuple[list[str], str]:
        ids: list[str] = []
        page_token: str | None = None
        history_id = ""
        after = _subtract_months(self.now(), self.settings.gmail_import_months)
        while True:
            page = await self.gmail.list_candidate_ids(after, page_token)
            ids.extend(message.id for message in page.messages)
            history_id = page.history_id or history_id
            page_token = page.next_page_token
            if not page_token:
                return list(dict.fromkeys(ids)), history_id

    async def _persist_messages(
        self, connection: EmailConnection, message_ids: list[str], history_id: str
    ) -> SyncResult:
        parsed_count = 0
        skipped_count = 0
        order_keys: set[tuple[str, str]] = set()
        message_hashes = {
            message_id: sha256(
                f"{self.message_id_pepper}:{message_id}".encode()
            ).hexdigest()
            for message_id in message_ids
        }
        async with self.session_factory() as session:
            existing_hashes = set(
                await session.scalars(
                    select(OrderSourceEvent.provider_message_id_hash).where(
                        OrderSourceEvent.connection_id == connection.id,
                        OrderSourceEvent.provider_message_id_hash.in_(
                            message_hashes.values()
                        ),
                    )
                )
            ) if message_hashes else set()
            pending = [
                (message_id, message_hash)
                for message_id, message_hash in message_hashes.items()
                if message_hash not in existing_hashes
            ]
            skipped_count += len(message_ids) - len(pending)
            for start in range(0, len(pending), _MESSAGE_FETCH_CONCURRENCY):
                batch = pending[start : start + _MESSAGE_FETCH_CONCURRENCY]
                raw_messages = await asyncio.gather(
                    *(self.gmail.get_message(message_id) for message_id, _ in batch)
                )
                for (_, message_hash), raw in zip(batch, raw_messages, strict=True):
                    email = normalize_message(raw, self.settings.gmail_max_message_bytes)
                    parser = next(
                        (item for item in self.parsers if item.matches(email)), None
                    )
                    observations = parser.parse(email) if parser else []
                    if not observations:
                        skipped_count += 1
                        continue
                    parsed_count += 1
                    for observation in observations:
                        await self._upsert_observation(
                            session, connection, observation, message_hash, parser
                        )
                        order_keys.add(
                            (
                                observation.marketplace.value,
                                observation.marketplace_order_id,
                            )
                        )
            await session.commit()
        return SyncResult(
            candidate_count=len(message_ids),
            parsed_count=parsed_count,
            skipped_count=skipped_count,
            order_count=len(order_keys),
            history_id=history_id,
        )

    async def _upsert_observation(
        self,
        session: AsyncSession,
        connection: EmailConnection,
        observation: OrderObservation,
        message_hash: str,
        parser: OrderEmailParser,
    ) -> None:
        order = await session.scalar(
            select(CommerceOrder).where(
                CommerceOrder.user_id == connection.user_id,
                CommerceOrder.marketplace == observation.marketplace,
                CommerceOrder.marketplace_order_id == observation.marketplace_order_id,
            )
        )
        is_newer = order is None or order.last_source_message_at is None or (
            observation.occurred_at >= order.last_source_message_at
        )
        if order is None:
            order = CommerceOrder(
                user_id=connection.user_id,
                marketplace=observation.marketplace,
                marketplace_order_id=observation.marketplace_order_id,
                status=observation.status,
            )
            session.add(order)
            await session.flush()
        if _STATUS_PRECEDENCE[observation.status] >= _STATUS_PRECEDENCE[order.status]:
            order.status = observation.status
        if observation.event_type == OrderEventType.PLACED and (
            order.placed_at is None or observation.occurred_at < order.placed_at
        ):
            order.placed_at = observation.occurred_at
        if is_newer:
            order.last_source_message_at = observation.occurred_at
            for field in (
                "currency",
                "total_amount",
                "expected_delivery_at",
                "delivered_at",
                "tracking_number",
                "carrier",
                "marketplace_url",
            ):
                value = getattr(observation, field)
                if value is not None:
                    setattr(order, field, value)
            if observation.items:
                await session.execute(
                    delete(CommerceOrderItem).where(CommerceOrderItem.order_id == order.id)
                )
                session.add_all(
                    [
                        CommerceOrderItem(order_id=order.id, **item.model_dump())
                        for item in observation.items
                    ]
                )
        session.add(
            OrderSourceEvent(
                order_id=order.id,
                connection_id=connection.id,
                provider_message_id_hash=message_hash,
                event_type=observation.event_type,
                event_at=observation.occurred_at,
                parser_name=getattr(parser, "name", parser.__class__.__name__),
                parser_version=getattr(parser, "version", "1"),
                facts=observation.model_dump(mode="json", exclude={"items"}),
            )
        )

    async def _finish(
        self,
        connection_id: UUID,
        status: EmailConnectionStatus,
        error_code: str | None,
        history_id: str | None = None,
    ) -> None:
        async with self.session_factory() as session:
            connection = await session.get(EmailConnection, connection_id)
            if connection is None:
                return
            connection.status = status
            connection.last_sync_error_code = error_code
            if error_code is None:
                connection.last_sync_completed_at = self.now()
            if history_id:
                connection.last_history_id = history_id
            await session.commit()

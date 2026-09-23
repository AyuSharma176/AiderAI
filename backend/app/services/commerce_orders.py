import base64
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    CommerceOrder,
    CommerceOrderItem,
    CommerceOrderStatus,
    Marketplace,
)


class InvalidOrderCursor(ValueError):
    pass


class CommerceOrderNotFound(LookupError):
    pass


@dataclass(frozen=True)
class CommerceOrderFilters:
    marketplace: Marketplace | None = None
    status: CommerceOrderStatus | None = None
    query: str | None = None
    cursor: str | None = None
    limit: int = 25


def encode_cursor(sort_at: datetime, order_id: UUID) -> str:
    value = f"{sort_at.isoformat()}|{order_id}"
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.b64decode(padded, altchars=b"-_", validate=True).decode()
        timestamp, order_id = decoded.rsplit("|", 1)
        return datetime.fromisoformat(timestamp), UUID(order_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidOrderCursor("Order cursor is invalid") from exc


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_commerce_orders(
    session: AsyncSession,
    user_id: UUID,
    filters: CommerceOrderFilters,
) -> tuple[list[CommerceOrder], str | None]:
    sort_at = func.coalesce(CommerceOrder.placed_at, CommerceOrder.created_at)
    statement = select(CommerceOrder).where(CommerceOrder.user_id == user_id)
    if filters.marketplace:
        statement = statement.where(CommerceOrder.marketplace == filters.marketplace)
    if filters.status:
        statement = statement.where(CommerceOrder.status == filters.status)
    if filters.query:
        pattern = f"%{_escape_like(filters.query.strip())}%"
        item_match = exists(
            select(CommerceOrderItem.id).where(
                CommerceOrderItem.order_id == CommerceOrder.id,
                CommerceOrderItem.title.ilike(pattern, escape="\\"),
            )
        )
        statement = statement.where(
            or_(CommerceOrder.marketplace_order_id.ilike(pattern, escape="\\"), item_match)
        )
    if filters.cursor:
        cursor_at, cursor_id = decode_cursor(filters.cursor)
        statement = statement.where(
            or_(sort_at < cursor_at, (sort_at == cursor_at) & (CommerceOrder.id < cursor_id))
        )
    rows = list(
        (
            await session.scalars(
                statement.order_by(sort_at.desc(), CommerceOrder.id.desc()).limit(
                    filters.limit + 1
                )
            )
        ).all()
    )
    has_more = len(rows) > filters.limit
    items = rows[: filters.limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(last.placed_at or last.created_at, last.id)
    return items, next_cursor


async def get_commerce_order(
    session: AsyncSession, user_id: UUID, order_id: UUID
) -> CommerceOrder:
    order = await session.scalar(
        select(CommerceOrder)
        .where(CommerceOrder.id == order_id, CommerceOrder.user_id == user_id)
        .options(
            selectinload(CommerceOrder.items),
            selectinload(CommerceOrder.events),
        )
    )
    if order is None:
        raise CommerceOrderNotFound("Order not found")
    return order

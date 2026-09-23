from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailConnection, Order, Ticket, User
from app.orders.parsers.base import validate_marketplace_url
from app.services.commerce_orders import (
    CommerceOrderFilters,
    CommerceOrderNotFound,
    get_commerce_order,
    list_commerce_orders,
)
from app.tools.schemas import (
    CreateTicketInput,
    FindMyOrdersByProductInput,
    GetMyOrderInput,
    ListMyOrdersInput,
    OrderStatusInput,
    ToolResult,
)


class ToolNotFoundError(LookupError):
    pass


class ToolValidationError(ValueError):
    pass


async def get_order_status(
    arguments: OrderStatusInput, user_id: UUID, session: AsyncSession
) -> ToolResult:
    order = await session.scalar(
        select(Order).where(
            Order.order_number == arguments.order_id,
            Order.user_id == user_id,
        )
    )
    if order is None:
        raise ToolNotFoundError("Order not found")
    return ToolResult(
        name="get_order_status",
        data={
            "order_id": order.order_number,
            "status": order.status,
            "tracking_number": order.tracking_number,
        },
    )


async def get_customer_profile(user_id: UUID, session: AsyncSession) -> ToolResult:
    user = await session.get(User, user_id)
    if user is None:
        raise ToolNotFoundError("Customer not found")
    return ToolResult(
        name="get_customer_profile",
        data={"id": str(user.id), "email": user.email, "name": user.name},
    )


async def create_support_ticket(
    arguments: CreateTicketInput, user_id: UUID, session: AsyncSession
) -> ToolResult:
    ticket = Ticket(user_id=user_id, issue=arguments.issue, status="open")
    session.add(ticket)
    await session.flush()
    return ToolResult(
        name="create_support_ticket",
        data={"ticket_id": ticket.id, "status": ticket.status},
    )


def _order_data(order) -> dict:
    return {
        "id": str(order.id),
        "marketplace": order.marketplace.value,
        "marketplace_order_id": order.marketplace_order_id,
        "status": order.status.value,
        "placed_at": order.placed_at.isoformat() if order.placed_at else None,
        "expected_delivery_at": (
            order.expected_delivery_at.isoformat() if order.expected_delivery_at else None
        ),
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "tracking_number": order.tracking_number,
        "carrier": order.carrier,
        "marketplace_url": (
            validate_marketplace_url(order.marketplace_url, order.marketplace)
            if order.marketplace_url
            else None
        ),
    }


async def _freshness(user_id: UUID, session: AsyncSession):
    return await session.scalar(
        select(EmailConnection.last_sync_completed_at).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == "gmail",
        )
    )


async def list_my_orders(
    arguments: ListMyOrdersInput, user_id: UUID, session: AsyncSession
) -> ToolResult:
    orders, _ = await list_commerce_orders(
        session,
        user_id,
        CommerceOrderFilters(
            marketplace=arguments.marketplace,
            status=arguments.status,
            limit=arguments.limit,
            since=arguments.since,
        ),
    )
    synced = await _freshness(user_id, session)
    return ToolResult(
        name="list_my_orders",
        data={
            "orders": [_order_data(order) for order in orders],
            "last_synced_at": synced.isoformat() if synced else None,
        },
    )


async def get_my_order(
    arguments: GetMyOrderInput, user_id: UUID, session: AsyncSession
) -> ToolResult:
    try:
        order = await get_commerce_order(session, user_id, arguments.order_id)
    except CommerceOrderNotFound:
        return ToolResult(name="get_my_order", data={"found": False})
    data = _order_data(order)
    data.update(
        {
            "found": True,
            "items": [
                {"title": item.title, "quantity": item.quantity} for item in order.items
            ],
            "timeline": [
                {"type": event.event_type.value, "at": event.event_at.isoformat()}
                for event in sorted(order.events, key=lambda item: item.event_at)
            ],
        }
    )
    return ToolResult(name="get_my_order", data=data)


async def find_my_orders_by_product(
    arguments: FindMyOrdersByProductInput, user_id: UUID, session: AsyncSession
) -> ToolResult:
    orders, _ = await list_commerce_orders(
        session,
        user_id,
        CommerceOrderFilters(query=arguments.query, limit=arguments.limit),
    )
    return ToolResult(
        name="find_my_orders_by_product",
        data={"orders": [_order_data(order) for order in orders]},
    )

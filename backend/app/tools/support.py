from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, Ticket, User
from app.tools.schemas import CreateTicketInput, OrderStatusInput, ToolResult


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
        data={"email": user.email, "name": user.name},
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

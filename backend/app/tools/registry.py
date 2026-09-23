from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.schemas import (
    CreateTicketInput,
    CustomerProfileInput,
    FindMyOrdersByProductInput,
    GetMyOrderInput,
    ListMyOrdersInput,
    OrderStatusInput,
    ToolResult,
)
from app.tools.support import (
    ToolValidationError,
    create_support_ticket,
    find_my_orders_by_product,
    get_customer_profile,
    get_my_order,
    get_order_status,
    list_my_orders,
)


class UnknownToolError(ValueError):
    pass


ToolHandler = Callable[[dict[str, Any], UUID, AsyncSession], Awaitable[ToolResult]]


async def _order_handler(
    arguments: dict[str, Any], user_id: UUID, session: AsyncSession
) -> ToolResult:
    return await get_order_status(OrderStatusInput.model_validate(arguments), user_id, session)


async def _profile_handler(
    arguments: dict[str, Any], user_id: UUID, session: AsyncSession
) -> ToolResult:
    CustomerProfileInput.model_validate(arguments)
    return await get_customer_profile(user_id, session)


async def _ticket_handler(
    arguments: dict[str, Any], user_id: UUID, session: AsyncSession
) -> ToolResult:
    return await create_support_ticket(
        CreateTicketInput.model_validate(arguments), user_id, session
    )


def _without_model_identity(arguments: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in arguments.items() if key != "user_id"}


async def _list_my_orders_handler(
    arguments: dict[str, Any], user_id: UUID, session: AsyncSession
) -> ToolResult:
    return await list_my_orders(
        ListMyOrdersInput.model_validate(_without_model_identity(arguments)), user_id, session
    )


async def _get_my_order_handler(
    arguments: dict[str, Any], user_id: UUID, session: AsyncSession
) -> ToolResult:
    return await get_my_order(
        GetMyOrderInput.model_validate(_without_model_identity(arguments)), user_id, session
    )


async def _find_my_orders_handler(
    arguments: dict[str, Any], user_id: UUID, session: AsyncSession
) -> ToolResult:
    return await find_my_orders_by_product(
        FindMyOrdersByProductInput.model_validate(_without_model_identity(arguments)),
        user_id,
        session,
    )


TOOL_REGISTRY: dict[str, ToolHandler] = {
    "get_order_status": _order_handler,
    "get_customer_profile": _profile_handler,
    "create_support_ticket": _ticket_handler,
    "list_my_orders": _list_my_orders_handler,
    "get_my_order": _get_my_order_handler,
    "find_my_orders_by_product": _find_my_orders_handler,
}


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    user_id: UUID,
    session: AsyncSession,
) -> ToolResult:
    handler = TOOL_REGISTRY.get(name)
    if handler is None:
        raise UnknownToolError("Requested tool is not available")
    try:
        return await handler(arguments, user_id, session)
    except ValidationError as exc:
        raise ToolValidationError("Tool arguments are invalid") from exc


class ToolRegistry:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute(self, name: str, arguments: dict[str, Any], user_id: UUID) -> ToolResult:
        return await execute_tool(name, arguments, user_id, self.session)

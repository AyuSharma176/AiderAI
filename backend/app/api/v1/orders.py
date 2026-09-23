from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models import CommerceOrderStatus, EmailConnection, Marketplace, User
from app.orders.parsers.base import validate_marketplace_url
from app.schemas.commerce_order import (
    CommerceOrderDetailResponse,
    CommerceOrderListResponse,
    CommerceOrderResponse,
)
from app.services.commerce_orders import (
    CommerceOrderFilters,
    CommerceOrderNotFound,
    InvalidOrderCursor,
    get_commerce_order,
    list_commerce_orders,
)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def _serialize_order(order) -> CommerceOrderResponse:
    response = CommerceOrderResponse.model_validate(order)
    response.marketplace_url = (
        validate_marketplace_url(response.marketplace_url, response.marketplace)
        if response.marketplace_url
        else None
    )
    return response


@router.get("", response_model=CommerceOrderListResponse)
async def list_orders_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    marketplace: Marketplace | None = None,
    status: CommerceOrderStatus | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CommerceOrderListResponse:
    try:
        orders, next_cursor = await list_commerce_orders(
            session,
            user.id,
            CommerceOrderFilters(marketplace, status, q, cursor, limit),
        )
    except InvalidOrderCursor as exc:
        raise HTTPException(422, detail="Order cursor is invalid") from exc
    last_sync = await session.scalar(
        select(EmailConnection.last_sync_completed_at).where(
            EmailConnection.user_id == user.id,
            EmailConnection.provider == "gmail",
        )
    )
    return CommerceOrderListResponse(
        items=[_serialize_order(order) for order in orders],
        next_cursor=next_cursor,
        last_sync_completed_at=last_sync,
    )


@router.get("/{order_id}", response_model=CommerceOrderDetailResponse)
async def get_order_endpoint(
    order_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CommerceOrderDetailResponse:
    try:
        order = await get_commerce_order(session, user.id, order_id)
    except CommerceOrderNotFound as exc:
        raise HTTPException(404, detail="Order not found") from exc
    response = CommerceOrderDetailResponse.model_validate(order)
    response.marketplace_url = (
        validate_marketplace_url(response.marketplace_url, response.marketplace)
        if response.marketplace_url
        else None
    )
    return response

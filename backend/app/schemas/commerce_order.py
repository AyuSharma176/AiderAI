from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import CommerceOrderStatus, Marketplace, OrderEventType


class CommerceOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    quantity: int
    unit_price: Decimal | None
    marketplace_product_id: str | None


class OrderSourceEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: OrderEventType
    event_at: datetime
    parser_name: str
    parser_version: str
    facts: dict[str, Any]


class CommerceOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    marketplace: Marketplace
    marketplace_order_id: str
    placed_at: datetime | None
    currency: str | None
    total_amount: Decimal | None
    status: CommerceOrderStatus
    expected_delivery_at: datetime | None
    delivered_at: datetime | None
    tracking_number: str | None
    carrier: str | None
    marketplace_url: str | None
    last_source_message_at: datetime | None
    items: list[CommerceOrderItemResponse] = []


class CommerceOrderDetailResponse(CommerceOrderResponse):
    events: list[OrderSourceEventResponse]


class CommerceOrderListResponse(BaseModel):
    items: list[CommerceOrderResponse]
    next_cursor: str | None
    last_sync_completed_at: datetime | None

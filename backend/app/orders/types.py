from datetime import datetime

from pydantic import BaseModel

from app.models import CommerceOrderStatus, Marketplace, OrderEventType


class CommerceEmail(BaseModel):
    provider_message_id: str
    history_id: str
    sent_at: datetime
    sender: str
    subject: str
    text: str


class OrderItemObservation(BaseModel):
    title: str
    quantity: int = 1
    unit_price: str | None = None
    marketplace_product_id: str | None = None


class OrderObservation(BaseModel):
    marketplace: Marketplace
    marketplace_order_id: str
    event_type: OrderEventType
    occurred_at: datetime
    status: CommerceOrderStatus
    items: list[OrderItemObservation] = []
    currency: str | None = None
    total_amount: str | None = None
    expected_delivery_at: datetime | None = None
    delivered_at: datetime | None = None
    tracking_number: str | None = None
    carrier: str | None = None
    marketplace_url: str | None = None

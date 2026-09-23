from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Marketplace(StrEnum):
    AMAZON = "amazon"
    FLIPKART = "flipkart"


class CommerceOrderStatus(StrEnum):
    PLACED = "placed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURN_UPDATE = "return_update"
    UNKNOWN = "unknown"


class OrderEventType(StrEnum):
    PLACED = "placed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURN_UPDATE = "return_update"
    UNKNOWN = "unknown"


class CommerceOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commerce_orders"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "marketplace",
            "marketplace_order_id",
            name="uq_commerce_order_owner_marketplace_id",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    marketplace: Mapped[Marketplace] = mapped_column(
        SqlEnum(Marketplace, native_enum=False), index=True
    )
    marketplace_order_id: Mapped[str] = mapped_column(String(120))
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[CommerceOrderStatus] = mapped_column(
        SqlEnum(CommerceOrderStatus, native_enum=False), index=True
    )
    expected_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(160), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(120), nullable=True)
    marketplace_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    last_source_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    user = relationship("User", back_populates="commerce_orders")
    items = relationship(
        "CommerceOrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    events = relationship(
        "OrderSourceEvent", back_populates="order", cascade="all, delete-orphan"
    )


class CommerceOrderItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commerce_order_items"

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("commerce_orders.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    marketplace_product_id: Mapped[str | None] = mapped_column(String(160), nullable=True)

    order = relationship("CommerceOrder", back_populates="items")


class OrderSourceEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "order_source_events"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "provider_message_id_hash",
            name="uq_order_source_connection_message",
        ),
    )

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("commerce_orders.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("email_connections.id", ondelete="CASCADE"), index=True
    )
    provider_message_id_hash: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[OrderEventType] = mapped_column(
        SqlEnum(OrderEventType, native_enum=False), index=True
    )
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    parser_name: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(32))
    facts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    order = relationship("CommerceOrder", back_populates="events")
    connection = relationship("EmailConnection", back_populates="source_events")

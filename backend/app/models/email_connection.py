from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmailConnectionStatus(StrEnum):
    CONNECTED = "connected"
    SYNCING = "syncing"
    RECONNECT_REQUIRED = "reconnect_required"
    DISCONNECTED = "disconnected"


class EmailConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_email_connection_user_provider"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="gmail")
    provider_account_id: Mapped[str] = mapped_column(String(255))
    email_address: Mapped[str] = mapped_column(String(320))
    encrypted_refresh_token: Mapped[str] = mapped_column(Text)
    granted_scopes: Mapped[str] = mapped_column(Text)
    status: Mapped[EmailConnectionStatus] = mapped_column(
        SqlEnum(EmailConnectionStatus, native_enum=False),
        default=EmailConnectionStatus.CONNECTED,
        index=True,
    )
    last_history_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_sync_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)

    user = relationship("User", back_populates="email_connections")
    source_events = relationship("OrderSourceEvent", back_populates="connection")

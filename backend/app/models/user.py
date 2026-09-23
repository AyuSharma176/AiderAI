from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))

    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    email_connections = relationship(
        "EmailConnection", back_populates="user", cascade="all, delete-orphan"
    )
    commerce_orders = relationship(
        "CommerceOrder", back_populates="user", cascade="all, delete-orphan"
    )
    tickets = relationship("Ticket", back_populates="user", cascade="all, delete-orphan")

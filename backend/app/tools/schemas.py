from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CommerceOrderStatus, Marketplace


class ToolResult(BaseModel):
    name: str
    data: dict[str, Any]


class OrderStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str

    @field_validator("order_id")
    @classmethod
    def normalize_order_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.startswith("ORD-") or len(normalized) > 40:
            raise ValueError("A valid ORD- identifier is required")
        return normalized


class CustomerProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str | None = None


class CreateTicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue: str = Field(min_length=10, max_length=2000)

    @field_validator("issue")
    @classmethod
    def normalize_issue(cls, value: str) -> str:
        normalized = value.strip()
        if not 10 <= len(normalized) <= 2000:
            raise ValueError("Issue must contain 10 to 2000 characters")
        return normalized


class ListMyOrdersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marketplace: Marketplace | None = None
    status: CommerceOrderStatus | None = None
    since: datetime | None = None
    limit: int = Field(default=10, ge=1, le=25)


class GetMyOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID


class FindMyOrdersByProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=10, ge=1, le=25)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Query is required")
        return normalized

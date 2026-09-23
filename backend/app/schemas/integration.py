from datetime import datetime

from pydantic import BaseModel

from app.models import EmailConnectionStatus, Marketplace


class GmailAuthorizationResponse(BaseModel):
    authorization_url: str


class GmailConnectionResponse(BaseModel):
    status: EmailConnectionStatus
    email_address: str | None = None
    last_sync_completed_at: datetime | None = None
    imported_order_count: int = 0
    marketplace_counts: dict[Marketplace, int] = {}
    reconnect_required: bool = False

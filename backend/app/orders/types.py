from datetime import datetime

from pydantic import BaseModel


class CommerceEmail(BaseModel):
    provider_message_id: str
    history_id: str
    sent_at: datetime
    sender: str
    subject: str
    text: str

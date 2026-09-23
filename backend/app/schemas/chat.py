from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    client_message_id: UUID = Field(default_factory=uuid4)

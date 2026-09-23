from typing import Literal

from pydantic import BaseModel, Field


ToolName = Literal["get_order_status", "create_support_ticket", "get_customer_profile"]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ContextChunk(BaseModel):
    text: str
    source: str
    page: int | None = None
    chunk_id: str | None = None
    score: float | None = None


class IntentDecision(BaseModel):
    route: Literal["knowledge", "tool", "direct"]
    tool_name: ToolName | None = None
    tool_arguments: dict[str, str] = Field(default_factory=dict)


class AnswerRequest(BaseModel):
    prompt: str


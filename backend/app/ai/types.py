from typing import Any, Literal

from pydantic import BaseModel, model_validator

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
    order_id: str | None = None
    issue: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_arguments(cls, value: Any) -> Any:
        if isinstance(value, dict) and isinstance(value.get("tool_arguments"), dict):
            value = {**value, **value["tool_arguments"]}
            value.pop("tool_arguments", None)
        return value

    @property
    def tool_arguments(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {"order_id": self.order_id, "issue": self.issue}.items()
            if value is not None
        }


class AnswerRequest(BaseModel):
    prompt: str
    system_instruction: str = "You are a customer-support assistant."

    def __contains__(self, value: str) -> bool:
        return value in self.prompt or value in self.system_instruction

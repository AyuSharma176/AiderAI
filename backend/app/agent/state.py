from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field

from app.ai.types import AnswerRequest, ChatMessage, ContextChunk, IntentDecision
from app.tools.schemas import ToolResult


class AgentEvent(BaseModel):
    type: Literal["conversation", "stage", "citation", "token"]
    data: dict[str, Any] = Field(default_factory=dict)


class GatewayProtocol(Protocol):
    async def classify_intent(self, messages: Sequence[ChatMessage]) -> IntentDecision: ...
    def stream_answer(self, request: AnswerRequest) -> AsyncIterator[str]: ...


type Retriever = Callable[[str, int], Awaitable[list[ContextChunk]]]
type ToolExecutor = Callable[[str, dict[str, str], UUID], Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class AgentDependencies:
    gateway: GatewayProtocol
    retriever: Retriever
    execute_tool: ToolExecutor
    retrieval_top_k: int = 5
    emit_event: Callable[[AgentEvent], Awaitable[None]] | None = None


class ConversationState(TypedDict, total=False):
    messages: list[ChatMessage]
    user_id: UUID
    intent: IntentDecision
    citations: list[ContextChunk]
    tool_result: ToolResult
    answer: str
    events: list[AgentEvent]

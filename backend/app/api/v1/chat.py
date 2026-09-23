import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import AgentDependencies, build_support_graph
from app.ai.gateway import AIUnavailableError, GeminiGateway, GoogleGenAITransport
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models import User
from app.rag.retrieval import retrieve
from app.schemas.chat import ChatRequest
from app.services.chat import execute_chat
from app.tools.registry import execute_tool

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def _frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'), default=str)}\n\n"


async def get_chat_graph(session: Annotated[AsyncSession, Depends(get_db)]):
    settings = get_settings()
    key = settings.gemini_api_key
    if key is None or not key.get_secret_value():
        raise AIUnavailableError("Gemini is not configured")
    gateway = GeminiGateway(
        GoogleGenAITransport(
            key.get_secret_value(),
            model=settings.gemini_chat_model,
            embedding_model=settings.gemini_embedding_model,
        )
    )

    async def retrieve_context(query: str, limit: int):
        return await retrieve(query, limit, session=session, gateway=gateway)

    async def run_tool(name: str, arguments: dict[str, str], user_id):
        return await execute_tool(name, arguments, user_id, session)

    return build_support_graph(AgentDependencies(gateway, retrieve_context, run_tool))


@router.post("/message")
async def chat_message(
    payload: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    graph: Annotated[object, Depends(get_chat_graph)],
) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        try:
            conversation, result = await execute_chat(
                session,
                user,
                graph,
                payload.content,
                payload.conversation_id,
            )
            for event in result.get("events", []):
                yield _frame(event.type, event.data)
            yield _frame(
                "complete",
                {
                    "conversation_id": str(conversation.id),
                    "message": result["answer"],
                },
            )
        except AIUnavailableError:
            yield _frame(
                "error",
                {"code": "ai_unavailable", "message": "AI service is unavailable"},
            )
        except Exception:  # noqa: BLE001 - SSE must terminate with a typed event
            yield _frame(
                "error",
                {"code": "chat_failed", "message": "Unable to complete the message"},
            )

    return StreamingResponse(stream(), media_type="text/event-stream")

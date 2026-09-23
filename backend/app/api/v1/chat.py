import asyncio
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
from app.services.rate_limit import enforce_chat_rate_limit
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

    def build(emit_event):
        return build_support_graph(
            AgentDependencies(
                gateway,
                retrieve_context,
                run_tool,
                retrieval_top_k=settings.retrieval_top_k,
                emit_event=emit_event,
            )
        )

    return build


@router.post("/message")
async def chat_message(
    payload: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    graph_factory: Annotated[object, Depends(get_chat_graph)],
    _rate_limit: Annotated[None, Depends(enforce_chat_rate_limit)],
) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        queue: asyncio.Queue = asyncio.Queue()
        emitted_graph_events = 0
        try:
            graph = graph_factory(queue.put) if callable(graph_factory) else graph_factory
            execution = asyncio.create_task(
                execute_chat(
                    session,
                    user,
                    graph,
                    payload.content,
                    payload.conversation_id,
                    client_message_id=payload.client_message_id,
                    event_sink=queue.put,
                )
            )
            while not execution.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    continue
                if event.type != "conversation":
                    emitted_graph_events += 1
                yield _frame(event.type, event.data)
            while not queue.empty():
                event = queue.get_nowait()
                if event.type != "conversation":
                    emitted_graph_events += 1
                yield _frame(event.type, event.data)
            conversation, result = await execution
            if emitted_graph_events == 0:
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

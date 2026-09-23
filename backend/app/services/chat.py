from collections.abc import Awaitable, Callable
from time import monotonic
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentEvent
from app.ai.types import ChatMessage
from app.middleware.request_context import get_request_id
from app.models import Message, MessageRole, User
from app.services.conversation import create_conversation, get_conversation
from app.services.observability import record_agent_event


async def execute_chat(
    session: AsyncSession,
    user: User,
    graph,
    content: str,
    conversation_id: UUID | None = None,
    *,
    client_message_id: UUID,
    event_sink: Callable[[AgentEvent], Awaitable[None]] | None = None,
):
    normalized = content.strip()
    if not normalized:
        raise ValueError("Message content is required")

    if conversation_id is None:
        conversation = await create_conversation(session, user, normalized[:60])
    else:
        conversation = await get_conversation(session, user, conversation_id)

    existing = await session.scalar(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.client_message_id == client_message_id,
        )
    )
    if existing is None:
        session.add(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=normalized,
                client_message_id=client_message_id,
            )
        )
        await session.commit()
    if event_sink is not None:
        await event_sink(
            AgentEvent(type="conversation", data={"conversation_id": str(conversation.id)})
        )

    history = list(
        (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at, Message.id)
            )
        ).all()
    )
    state = {
        "messages": [
            ChatMessage(role=message.role.value, content=message.content) for message in history
        ],
        "user_id": user.id,
        "events": [],
    }
    started = monotonic()
    try:
        result = await graph.ainvoke(state)
    except Exception:
        await record_agent_event(
            session,
            event_type="chat_failed",
            request_id=get_request_id(),
            conversation_id=conversation.id,
            latency_ms=int((monotonic() - started) * 1000),
            success=False,
            safe_metadata={"message_count": len(history)},
        )
        await session.commit()
        raise

    citations = [
        citation.model_dump(mode="json", exclude={"text"}, exclude_none=True)
        for citation in result.get("citations", [])
    ]
    tool_result = result.get("tool_result")
    session.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=result["answer"],
            citations=citations or None,
            tool_metadata=(
                tool_result.model_dump(mode="json", exclude_none=True) if tool_result else None
            ),
        )
    )
    await record_agent_event(
        session,
        event_type="chat_completed",
        request_id=get_request_id(),
        conversation_id=conversation.id,
        latency_ms=int((monotonic() - started) * 1000),
        tool_name=result.get("intent").tool_name if result.get("intent") else None,
        safe_metadata={
            "message_count": len(history),
            "retrieval_count": len(result.get("citations", [])),
            "token_count": sum(1 for event in result.get("events", []) if event.type == "token"),
        },
    )
    conversation.updated_at = func.now()
    await session.commit()
    return conversation, result

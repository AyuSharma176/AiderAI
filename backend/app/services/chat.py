from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import ChatMessage
from app.models import Message, MessageRole, User
from app.services.conversation import create_conversation, get_conversation


async def execute_chat(
    session: AsyncSession,
    user: User,
    graph,
    content: str,
    conversation_id: UUID | None = None,
):
    normalized = content.strip()
    if not normalized:
        raise ValueError("Message content is required")

    if conversation_id is None:
        conversation = await create_conversation(session, user, normalized[:60])
    else:
        conversation = await get_conversation(session, user, conversation_id)

    session.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=normalized,
        )
    )
    await session.commit()

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
            ChatMessage(role=message.role.value, content=message.content)
            for message in history
        ],
        "user_id": user.id,
        "events": [],
    }
    result = await graph.ainvoke(state)

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
                tool_result.model_dump(mode="json", exclude_none=True)
                if tool_result
                else None
            ),
        )
    )
    await session.commit()
    return conversation, result

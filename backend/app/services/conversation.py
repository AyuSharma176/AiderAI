from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Conversation, User


class ConversationNotFoundError(LookupError):
    pass


async def create_conversation(session: AsyncSession, user: User, title: str) -> Conversation:
    conversation = Conversation(user_id=user.id, title=title.strip() or "New conversation")
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def list_conversations(session: AsyncSession, user: User) -> list[Conversation]:
    result = await session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.all())


async def get_conversation(
    session: AsyncSession, user: User, conversation_id: UUID
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise ConversationNotFoundError("Conversation not found")
    return conversation


async def delete_conversation(session: AsyncSession, user: User, conversation_id: UUID) -> None:
    result = await session.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if result.rowcount == 0:
        raise ConversationNotFoundError("Conversation not found")
    await session.commit()

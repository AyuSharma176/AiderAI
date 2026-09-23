import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.state import AgentEvent
from app.ai.gateway import AIUnavailableError
from app.ai.types import ContextChunk
from app.api.dependencies import get_current_user
from app.api.v1.chat import get_chat_graph
from app.core.database import get_db
from app.models import Base, Message, MessageRole, User


class SuccessfulGraph:
    async def ainvoke(self, state):
        return {
            **state,
            "answer": "Your refund takes five days.",
            "citations": [ContextChunk(text="five days", source="refund.pdf", page=2)],
            "events": [
                AgentEvent(type="stage", data={"name": "retrieving"}),
                AgentEvent(type="citation", data={"source": "refund.pdf", "page": 2}),
                AgentEvent(type="token", data={"text": "Your refund takes five days."}),
            ],
        }


class FailingGraph:
    async def ainvoke(self, state):
        raise AIUnavailableError("provider disconnected")


@pytest.fixture
async def chat_context(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-at-least-thirty-two-bytes")
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user = User(email="chat@example.com", name="Chat", password_hash="hash")
        session.add(user)
        await session.commit()

    async def override_db():
        async with sessions() as session:
            yield session

    async def override_user():
        return user

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_chat_graph] = lambda: SuccessfulGraph()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, sessions, app
    await engine.dispose()


@pytest.mark.asyncio
async def test_stream_sequence_and_successful_persistence(chat_context) -> None:
    client, sessions, _ = chat_context

    async with client.stream(
        "POST", "/api/v1/chat/message", json={"content": "What is the refund policy?"}
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert body.index("event: stage") < body.index("event: citation")
    assert body.index("event: citation") < body.index("event: token")
    assert body.index("event: token") < body.index("event: complete")
    async with sessions() as session:
        roles = list((await session.scalars(select(Message.role))).all())
    assert roles == [MessageRole.USER, MessageRole.ASSISTANT]


@pytest.mark.asyncio
async def test_stream_failure_is_typed_and_does_not_save_partial_assistant(
    chat_context,
) -> None:
    client, sessions, app = chat_context
    app.dependency_overrides[get_chat_graph] = lambda: FailingGraph()

    async with client.stream(
        "POST", "/api/v1/chat/message", json={"content": "hello"}
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert "event: error" in body
    assert '"code":"ai_unavailable"' in body
    async with sessions() as session:
        count = await session.scalar(
            select(func.count()).select_from(Message).where(
                Message.role == MessageRole.ASSISTANT
            )
        )
    assert count == 0

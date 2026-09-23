from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models import Base, Conversation, Message, MessageRole, User


@pytest.fixture
async def conversation_context(monkeypatch: pytest.MonkeyPatch):
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
        user_a = User(email="a@example.com", name="A", password_hash="hash")
        user_b = User(email="b@example.com", name="B", password_hash="hash")
        session.add_all([user_a, user_b])
        await session.flush()
        foreign = Conversation(user_id=user_b.id, title="Private")
        session.add(foreign)
        await session.commit()

    async def override_db():
        async with sessions() as session:
            yield session

    async def override_user():
        return user_a

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, sessions, user_a, foreign
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_list_and_ordered_history(conversation_context) -> None:
    client, sessions, user, _ = conversation_context
    created = await client.post("/api/v1/conversations", json={"title": "Returns"})
    assert created.status_code == 201
    conversation_id = UUID(created.json()["id"])
    async with sessions() as session:
        session.add_all(
            [
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.USER,
                    content="first",
                ),
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content="second",
                ),
            ]
        )
        await session.commit()

    listing = await client.get("/api/v1/conversations")
    detail = await client.get(f"/api/v1/conversations/{conversation_id}")

    assert listing.status_code == 200
    assert listing.json()[0]["user_id"] == str(user.id)
    assert [message["content"] for message in detail.json()["messages"]] == [
        "first",
        "second",
    ]


@pytest.mark.asyncio
async def test_foreign_conversation_returns_404(conversation_context) -> None:
    client, _, _, foreign = conversation_context

    response = await client.get(f"/api/v1/conversations/{foreign.id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_is_scoped_to_owner(conversation_context) -> None:
    client, _, _, foreign = conversation_context

    response = await client.delete(f"/api/v1/conversations/{foreign.id}")

    assert response.status_code == 404

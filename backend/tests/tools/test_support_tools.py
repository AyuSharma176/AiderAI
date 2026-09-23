import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Order, Ticket, User
from app.tools.registry import ToolRegistry, UnknownToolError
from app.tools.support import ToolNotFoundError, ToolValidationError


@pytest.fixture
async def tool_context():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user_a = User(email="a@example.com", name="User A", password_hash="hash")
        user_b = User(email="b@example.com", name="User B", password_hash="hash")
        session.add_all([user_a, user_b])
        await session.flush()
        order_a = Order(
            order_number="ORD-1001",
            user_id=user_a.id,
            status="shipped",
            tracking_number="TRACK-1",
        )
        order_b = Order(
            order_number="ORD-2001",
            user_id=user_b.id,
            status="processing",
        )
        session.add_all([order_a, order_b])
        await session.commit()
        yield ToolRegistry(session), session, user_a, user_b, order_a, order_b
    await engine.dispose()


@pytest.mark.asyncio
async def test_owned_order_returns_serializable_status(tool_context) -> None:
    registry, _, user_a, _, order_a, _ = tool_context

    result = await registry.execute("get_order_status", {"order_id": " ord-1001 "}, user_a.id)

    assert result.data == {
        "order_id": order_a.order_number,
        "status": "shipped",
        "tracking_number": "TRACK-1",
    }


@pytest.mark.asyncio
async def test_foreign_order_is_indistinguishable_from_missing(tool_context) -> None:
    registry, _, user_a, _, _, order_b = tool_context

    with pytest.raises(ToolNotFoundError):
        await registry.execute("get_order_status", {"order_id": order_b.order_number}, user_a.id)


@pytest.mark.asyncio
async def test_profile_ignores_model_supplied_identity(tool_context) -> None:
    registry, _, user_a, user_b, _, _ = tool_context

    result = await registry.execute("get_customer_profile", {"user_id": str(user_b.id)}, user_a.id)

    assert result.data == {
        "id": str(user_a.id),
        "email": user_a.email,
        "name": user_a.name,
    }


@pytest.mark.asyncio
async def test_ticket_requires_meaningful_issue_and_is_owned(tool_context) -> None:
    registry, session, user_a, _, _, _ = tool_context

    with pytest.raises(ToolValidationError):
        await registry.execute("create_support_ticket", {"issue": " too short "}, user_a.id)

    result = await registry.execute(
        "create_support_ticket",
        {"issue": " My package arrived with a damaged seal. "},
        user_a.id,
    )
    ticket = await session.scalar(select(Ticket).where(Ticket.id == result.data["ticket_id"]))

    assert result.data["status"] == "open"
    assert ticket is not None and ticket.user_id == user_a.id
    assert ticket.issue == "My package arrived with a damaged seal."


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected(tool_context) -> None:
    registry, _, user_a, _, _, _ = tool_context

    with pytest.raises(UnknownToolError):
        await registry.execute("run_shell", {"command": "whoami"}, user_a.id)

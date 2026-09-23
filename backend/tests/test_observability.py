import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import AgentExecutionLog, Base
from app.services.observability import record_agent_event, redact_sensitive


def test_recursive_redaction_removes_secret_values() -> None:
    value = {
        "authorization": "Bearer secret-token",
        "nested": {"password": "guess-me", "count": 3},
        "safe": "visible",
    }

    redacted = redact_sensitive(value)

    assert redacted == {
        "authorization": "[REDACTED]",
        "nested": {"password": "[REDACTED]", "count": 3},
        "safe": "visible",
    }
    assert "secret-token" not in str(redacted)


@pytest.mark.asyncio
async def test_execution_record_keeps_only_safe_operational_metadata() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        record = await record_agent_event(
            session,
            event_type="retrieval",
            request_id="req-1",
            model="gemini-test",
            latency_ms=12,
            success=True,
            safe_metadata={"retrieval_count": 2, "prompt": "private question"},
        )
        await session.commit()
        persisted = await session.get(AgentExecutionLog, record.id)

    assert persisted is not None
    assert persisted.safe_metadata == {"retrieval_count": 2}
    await engine.dispose()

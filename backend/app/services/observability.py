from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentExecutionLog

SENSITIVE_PARTS = ("authorization", "cookie", "password", "token", "secret", "api_key")
SAFE_METADATA_KEYS = {
    "retrieval_count",
    "token_count",
    "message_count",
    "chunk_count",
    "result_count",
}


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if any(part in key.lower() for part in SENSITIVE_PARTS)
                else redact_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


async def record_agent_event(
    session: AsyncSession,
    *,
    event_type: str,
    request_id: str | None = None,
    conversation_id=None,
    model: str | None = None,
    latency_ms: int | None = None,
    tool_name: str | None = None,
    success: bool = True,
    safe_metadata: dict[str, Any] | None = None,
) -> AgentExecutionLog:
    filtered = {
        key: value
        for key, value in (safe_metadata or {}).items()
        if key in SAFE_METADATA_KEYS and isinstance(value, (int, float))
    }
    record = AgentExecutionLog(
        conversation_id=conversation_id,
        request_id=request_id,
        event_type=event_type,
        model=model,
        latency_ms=latency_ms,
        tool_name=tool_name,
        success=success,
        safe_metadata=filtered or None,
    )
    session.add(record)
    await session.flush()
    return record

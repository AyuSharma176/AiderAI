import asyncio

from app.integrations.gmail.client import GmailAuthenticationError, GmailRateLimited
from app.workers.order_tasks import is_transient_sync_error, process_sync


class RecordingRunner:
    def __init__(self, record: dict[str, list]) -> None:
        self.record = record

    async def sync(self, connection_id: str, mode: str) -> None:
        self.record["loops"].append(asyncio.get_running_loop())
        self.record["calls"].append((connection_id, mode))

    async def dispose(self) -> None:
        self.record["disposed"].append(True)


def test_two_sequential_jobs_create_and_dispose_separate_event_loops() -> None:
    record: dict[str, list] = {"loops": [], "calls": [], "disposed": []}

    process_sync("connection-1", "auto", lambda: RecordingRunner(record))
    process_sync("connection-2", "full", lambda: RecordingRunner(record))

    assert record["loops"][0] is not record["loops"][1]
    assert record["calls"] == [("connection-1", "auto"), ("connection-2", "full")]
    assert record["disposed"] == [True, True]


def test_retry_classification_excludes_invalid_grants() -> None:
    assert is_transient_sync_error(GmailRateLimited("quota")) is True
    assert is_transient_sync_error(GmailAuthenticationError("expired")) is False
    assert is_transient_sync_error(ValueError("bad configuration")) is False

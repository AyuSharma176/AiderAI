import pytest

from app.ai.gateway import AIUnavailableError
from app.workers.tasks import is_transient_error, run_document_processing


class RecordingIngestor:
    def __init__(self) -> None:
        self.processed: list[str] = []

    async def process(self, document_id: str) -> None:
        self.processed.append(document_id)


@pytest.mark.asyncio
async def test_worker_delegates_to_ingestor() -> None:
    ingestor = RecordingIngestor()

    await run_document_processing("doc-123", ingestor)

    assert ingestor.processed == ["doc-123"]


def test_only_transient_provider_errors_are_retried() -> None:
    assert is_transient_error(AIUnavailableError("offline")) is True
    assert is_transient_error(ValueError("bad document")) is False

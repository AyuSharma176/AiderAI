import asyncio
from typing import Protocol

from sqlalchemy.exc import DBAPIError, OperationalError

from app.ai.gateway import AIUnavailableError, GeminiGateway, GoogleGenAITransport
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.rag.ingestion import DocumentIngestor
from app.workers.celery_app import celery_app


class Ingestor(Protocol):
    async def process(self, document_id: str) -> None: ...


def is_transient_error(exc: Exception) -> bool:
    return isinstance(exc, (AIUnavailableError, OperationalError, DBAPIError))


async def run_document_processing(document_id: str, ingestor: Ingestor) -> None:
    await ingestor.process(document_id)


def _build_ingestor() -> DocumentIngestor:
    settings = get_settings()
    api_key = settings.gemini_api_key
    if api_key is None or not api_key.get_secret_value():
        raise RuntimeError("GEMINI_API_KEY is required for document processing")
    transport = GoogleGenAITransport(
        api_key.get_secret_value(),
        model=settings.gemini_chat_model,
        embedding_model=settings.gemini_embedding_model,
    )
    return DocumentIngestor(get_session_factory(), GeminiGateway(transport))


@celery_app.task(bind=True, max_retries=3, name="documents.process")
def process_document(self, document_id: str) -> None:
    try:
        asyncio.run(run_document_processing(document_id, _build_ingestor()))
    except Exception as exc:
        if is_transient_error(exc):
            raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc
        raise

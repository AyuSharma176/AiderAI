import asyncio
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai.gateway import AIUnavailableError, GeminiGateway, GoogleGenAITransport
from app.core.config import get_settings
from app.models import Document, DocumentStatus
from app.rag.ingestion import DocumentIngestor
from app.workers.celery_app import celery_app


class Ingestor(Protocol):
    async def process(self, document_id: str) -> None: ...


def is_transient_error(exc: Exception) -> bool:
    return isinstance(exc, (AIUnavailableError, OperationalError, DBAPIError))


async def run_document_processing(document_id: str, ingestor: Ingestor) -> None:
    await ingestor.process(document_id)


def _build_gateway() -> GeminiGateway:
    settings = get_settings()
    api_key = settings.gemini_api_key
    if api_key is None or not api_key.get_secret_value():
        raise RuntimeError("GEMINI_API_KEY is required for document processing")
    transport = GoogleGenAITransport(
        api_key.get_secret_value(),
        model=settings.gemini_chat_model,
        embedding_model=settings.gemini_embedding_model,
    )
    return GeminiGateway(transport)


async def _run_configured(document_id: str, *, final_attempt: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        try:
            gateway = _build_gateway()
        except Exception:
            async with sessions() as session:
                document = await session.get(Document, UUID(str(document_id)))
                if document is not None:
                    document.status = DocumentStatus.FAILED
                    document.error_message = "Document processing is not configured."
                    await session.commit()
            raise
        ingestor = DocumentIngestor(sessions, gateway)
        await ingestor.process(document_id, mark_failure=False)
    except Exception as exc:
        if "ingestor" in locals() and (final_attempt or not is_transient_error(exc)):
            await ingestor.mark_failed(document_id, exc)
        raise
    finally:
        await engine.dispose()


@celery_app.task(bind=True, max_retries=3, name="documents.process")
def process_document(self, document_id: str) -> None:
    logger = structlog.get_logger()
    logger.info(
        "document_processing_started", document_id=document_id, attempt=self.request.retries
    )
    try:
        asyncio.run(
            _run_configured(
                document_id,
                final_attempt=self.request.retries >= self.max_retries,
            )
        )
        logger.info("document_processing_completed", document_id=document_id)
    except Exception as exc:
        logger.exception(
            "document_processing_failed",
            document_id=document_id,
            attempt=self.request.retries,
            transient=is_transient_error(exc),
        )
        if is_transient_error(exc) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2**self.request.retries) from exc
        raise

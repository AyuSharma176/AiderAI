from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.gateway import GeminiGateway
from app.models import Document, DocumentChunk, DocumentStatus
from app.rag.chunking import PageText, chunk_pages
from app.rag.pdf import EmptyPDFError, extract_pdf_pages

PageExtractor = Callable[[str | Path], Sequence[PageText]]


class DocumentIngestor:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: GeminiGateway,
        *,
        extract_pages: PageExtractor = extract_pdf_pages,
    ) -> None:
        self.session_factory = session_factory
        self.gateway = gateway
        self.extract_pages = extract_pages

    async def process(self, document_id: UUID | str) -> None:
        async with self.session_factory() as session:
            document = await session.get(Document, document_id)
            if document is None:
                raise LookupError("Document not found")
            document.status = DocumentStatus.PROCESSING
            document.error_message = None
            storage_path = document.storage_path
            await session.commit()

        try:
            pages = list(self.extract_pages(storage_path))
            chunks = chunk_pages(pages)
            if not chunks:
                raise EmptyPDFError("PDF contains no readable text")

            embeddings: list[list[float]] = []
            for start in range(0, len(chunks), 64):
                batch = chunks[start : start + 64]
                embeddings.extend(
                    await self.gateway.embed_texts([chunk.text for chunk in batch])
                )

            async with self.session_factory() as session:
                document = await session.get(Document, document_id)
                if document is None:
                    raise LookupError("Document not found")
                await session.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
                )
                session.add_all(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=chunk.chunk_index,
                        page_number=chunk.page_number,
                        text=chunk.text,
                        embedding=embedding,
                    )
                    for chunk, embedding in zip(chunks, embeddings, strict=True)
                )
                document.status = DocumentStatus.READY
                document.error_message = None
                await session.commit()
        except Exception as exc:
            await self._mark_failed(document_id, exc)
            raise

    async def _mark_failed(self, document_id: UUID | str, exc: Exception) -> None:
        message = (
            "PDF contains no readable text."
            if isinstance(exc, EmptyPDFError)
            else "Document processing failed. Please try again."
        )
        async with self.session_factory() as session:
            document = await session.get(Document, document_id)
            if document is not None:
                document.status = DocumentStatus.FAILED
                document.error_message = message
                await session.commit()

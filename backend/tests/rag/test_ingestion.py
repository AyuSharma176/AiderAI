from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Document, DocumentChunk, DocumentStatus
from app.rag.chunking import PageText
from app.rag.ingestion import DocumentIngestor
from app.rag.pdf import EmptyPDFError, extract_pdf_pages


class FakeGateway:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(index % 2) for index in range(768)] for _ in texts]


@pytest.mark.asyncio
async def test_reprocessing_replaces_chunks(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        document = Document(
            filename="guide.pdf",
            content_type="application/pdf",
            storage_path=str(tmp_path / "guide.pdf"),
        )
        session.add(document)
        await session.commit()
        document_id = document.id

    ingestor = DocumentIngestor(
        sessions,
        FakeGateway(),
        extract_pages=lambda _: [PageText(page_number=1, text="support policy " * 100)],
    )
    await ingestor.process(document_id)
    async with sessions() as session:
        first_count = await session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
    await ingestor.process(document_id)
    async with sessions() as session:
        second_count = await session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
        persisted = await session.get(Document, document_id)

    assert first_count and second_count == first_count
    assert persisted is not None and persisted.status == DocumentStatus.READY
    await engine.dispose()


def test_empty_pdf_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class EmptyReader:
        def __init__(self, _: str) -> None:
            self.pages: list[object] = []

    monkeypatch.setattr("app.rag.pdf.PdfReader", EmptyReader)

    with pytest.raises(EmptyPDFError, match="readable text"):
        extract_pdf_pages(tmp_path / "empty.pdf")

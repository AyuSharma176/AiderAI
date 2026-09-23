import math
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import GeminiGateway
from app.ai.types import ContextChunk
from app.models import Document, DocumentChunk, DocumentStatus

type RetrievalRow = tuple[str, str, int | None, str, Sequence[float]]


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    return numerator / denominator if denominator else 0.0


def rank_context_chunks(
    query_embedding: Sequence[float], rows: Sequence[RetrievalRow], *, limit: int = 5
) -> list[ContextChunk]:
    scored = [
        (
            _cosine_similarity(query_embedding, embedding),
            ContextChunk(
                text=text,
                source=source,
                page=page,
                chunk_id=chunk_id,
            ),
        )
        for text, source, page, chunk_id, embedding in rows
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk.model_copy(update={"score": score}) for score, chunk in scored[:limit]]


async def retrieve(
    query: str,
    limit: int = 5,
    *,
    session: AsyncSession,
    gateway: GeminiGateway,
) -> list[ContextChunk]:
    query_vectors = await gateway.embed_texts([query])
    distance = DocumentChunk.embedding.cosine_distance(query_vectors[0])
    statement = (
        select(DocumentChunk, Document.filename, distance.label("distance"))
        .join(Document)
        .where(Document.status == DocumentStatus.READY)
        .order_by(distance)
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return [
        ContextChunk(
            text=chunk.text,
            source=filename,
            page=chunk.page_number,
            chunk_id=str(chunk.id),
            score=max(0.0, 1.0 - float(row_distance)),
        )
        for chunk, filename, row_distance in rows
    ]

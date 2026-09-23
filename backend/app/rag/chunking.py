from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_index: int
    page_number: int
    text: str


def chunk_pages(pages: Sequence[PageText], size: int = 1000, overlap: int = 150) -> list[TextChunk]:
    if size <= 0:
        raise ValueError("Chunk size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("Chunk overlap must be non-negative and smaller than size")

    chunks: list[TextChunk] = []
    step = size - overlap
    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        for start in range(0, len(text), step):
            value = text[start : start + size]
            if not value:
                break
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    page_number=page.page_number,
                    text=value,
                )
            )
            if start + size >= len(text):
                break
    return chunks

from pathlib import Path

from pypdf import PdfReader

from app.rag.chunking import PageText


class EmptyPDFError(ValueError):
    pass


def extract_pdf_pages(path: str | Path) -> list[PageText]:
    reader = PdfReader(str(path))
    pages = [
        PageText(page_number=index, text=(page.extract_text() or "").strip())
        for index, page in enumerate(reader.pages, start=1)
    ]
    readable = [page for page in pages if page.text]
    if not readable:
        raise EmptyPDFError("PDF contains no readable text")
    return readable

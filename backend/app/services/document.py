from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Document


class InvalidPDFError(ValueError):
    pass


class FileTooLargeError(ValueError):
    pass


class DocumentNotFoundError(LookupError):
    pass


async def store_pdf(session: AsyncSession, upload: UploadFile, settings: Settings) -> Document:
    filename = (upload.filename or "").strip()
    if Path(filename).suffix.lower() != ".pdf" or upload.content_type != "application/pdf":
        raise InvalidPDFError("Choose a PDF file")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = upload_dir / f"{uuid4()}.pdf"
    total = 0
    signature = bytearray()
    try:
        with storage_path.open("wb") as destination:
            while chunk := await upload.read(64 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise FileTooLargeError("PDF exceeds the configured size limit")
                if len(signature) < 5:
                    signature.extend(chunk[: 5 - len(signature)])
                destination.write(chunk)
        if bytes(signature) != b"%PDF-":
            raise InvalidPDFError("File does not contain a PDF signature")
    except Exception:
        storage_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    document = Document(
        filename=Path(filename).name,
        content_type="application/pdf",
        storage_path=str(storage_path),
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def list_documents(session: AsyncSession) -> list[Document]:
    documents = await session.scalars(select(Document).order_by(Document.created_at.desc()))
    return list(documents.all())


async def get_document(session: AsyncSession, document_id: UUID) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError("Document not found")
    return document

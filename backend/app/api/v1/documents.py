from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models import User
from app.schemas.document import DocumentResponse
from app.services.document import (
    DocumentNotFoundError,
    FileTooLargeError,
    InvalidPDFError,
    get_document,
    list_documents,
    store_pdf,
)
from app.workers.tasks import process_document

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
type DocumentDispatcher = Callable[[str], object]


def get_document_dispatcher() -> DocumentDispatcher:
    return process_document.delay


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    dispatch: Annotated[DocumentDispatcher, Depends(get_document_dispatcher)],
):
    try:
        document = await store_pdf(session, file, settings)
    except InvalidPDFError as exc:
        return JSONResponse(
            status_code=422,
            content={"code": "invalid_pdf", "message": str(exc)},
        )
    except FileTooLargeError as exc:
        return JSONResponse(
            status_code=413,
            content={"code": "file_too_large", "message": str(exc)},
        )
    dispatch(str(document.id))
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> list[DocumentResponse]:
    return [
        DocumentResponse.model_validate(document)
        for document in await list_documents(session)
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_endpoint(
    document_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> DocumentResponse:
    try:
        document = await get_document(session, document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return DocumentResponse.model_validate(document)

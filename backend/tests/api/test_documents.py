from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_user
from app.api.v1.documents import get_document_dispatcher
from app.core.database import get_db
from app.models import Base, Document, DocumentStatus, User


@pytest.fixture
async def document_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-at-least-thirty-two-bytes")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "64")
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user = User(email="docs@example.com", name="Docs", password_hash="hash")
        session.add(user)
        await session.commit()

    dispatched: list[str] = []

    async def override_db():
        async with sessions() as session:
            yield session

    async def override_user():
        return user

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_document_dispatcher] = lambda: dispatched.append
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, sessions, dispatched, tmp_path / "uploads"
    await engine.dispose()


@pytest.mark.asyncio
async def test_valid_pdf_is_stored_safely_and_queued(document_context) -> None:
    client, _, dispatched, upload_dir = document_context

    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("policy.pdf", b"%PDF-1.4\nvalid", "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert "storage_path" not in response.json()
    assert dispatched == [response.json()["id"]]
    stored = list(upload_dir.iterdir())
    assert len(stored) == 1 and stored[0].suffix == ".pdf"
    assert stored[0].name != "policy.pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("policy.txt", b"%PDF-1.4", "application/pdf"),
        ("policy.pdf", b"%PDF-1.4", "text/plain"),
        ("policy.pdf", b"not-a-pdf", "application/pdf"),
    ],
)
async def test_invalid_pdf_metadata_or_signature_is_rejected(
    document_context, filename, content, content_type
) -> None:
    client, _, dispatched, upload_dir = document_context

    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, content, content_type)},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_pdf"
    assert dispatched == []
    assert not upload_dir.exists() or list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_oversize_pdf_is_rejected_and_partial_file_removed(document_context) -> None:
    client, _, _, upload_dir = document_context

    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("large.pdf", b"%PDF-" + b"x" * 100, "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"
    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_list_and_detail_include_safe_failure_status(document_context) -> None:
    client, sessions, _, _ = document_context
    async with sessions() as session:
        document = Document(
            filename="broken.pdf",
            content_type="application/pdf",
            storage_path="C:/secret/internal/path.pdf",
            status=DocumentStatus.FAILED,
            error_message="Document processing failed. Please try again.",
        )
        session.add(document)
        await session.commit()

    listing = await client.get("/api/v1/documents")
    detail = await client.get(f"/api/v1/documents/{document.id}")

    assert listing.status_code == 200
    assert listing.json()[0]["status"] == "failed"
    assert detail.json()["error_message"] == "Document processing failed. Please try again."
    assert "storage_path" not in detail.json()

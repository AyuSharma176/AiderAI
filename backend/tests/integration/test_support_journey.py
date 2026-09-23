from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.graph import AgentDependencies, build_support_graph
from app.ai.types import ContextChunk, IntentDecision
from app.api.v1.chat import get_chat_graph
from app.api.v1.documents import get_document_dispatcher
from app.core.database import get_db
from app.models import Base
from app.rag.chunking import PageText
from app.rag.ingestion import DocumentIngestor


class FakeGemini:
    async def classify_intent(self, messages):
        return IntentDecision(route="knowledge")

    async def embed_texts(self, texts):
        return [[1.0] * 768 for _ in texts]

    async def stream_answer(self, request):
        assert "Refunds take five business days." in request.prompt
        yield "Refunds take "
        yield "five business days."


@pytest.mark.asyncio
async def test_support_journey(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "journey-secret-that-is-at-least-thirty-two-bytes")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        async with sessions() as session:
            yield session

    queued: list[str] = []
    fake_gemini = FakeGemini()

    async def retrieve_policy(query: str, limit: int):
        assert query == "What is the refund policy?"
        return [
            ContextChunk(
                text="Refunds take five business days.",
                source="policy.pdf",
                page=1,
            )
        ]

    async def reject_tools(name, arguments, user_id):
        raise AssertionError("Knowledge journey must not execute a tool")

    graph = build_support_graph(AgentDependencies(fake_gemini, retrieve_policy, reject_tools))
    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_document_dispatcher] = lambda: queued.append
    app.dependency_overrides[get_chat_graph] = lambda: graph

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "journey@example.com",
                "name": "Journey",
                "password": "StrongJourney123!",
            },
        )
        token = registered.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        uploaded = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("policy.pdf", b"%PDF-1.4\nfake", "application/pdf")},
        )
        document = uploaded.json()
        assert queued == [document["id"]]

        ingestor = DocumentIngestor(
            sessions,
            fake_gemini,
            extract_pages=lambda _: [
                PageText(page_number=1, text="Refunds take five business days.")
            ],
        )
        await ingestor.process(document["id"])
        ready = await client.get(f"/api/v1/documents/{document['id']}", headers=headers)
        assert ready.json()["status"] == "ready"

        chat = await client.post(
            "/api/v1/chat/message",
            headers=headers,
            json={"content": "What is the refund policy?"},
        )

    assert "event: citation" in chat.text
    assert '"source":"policy.pdf"' in chat.text
    assert "five business days." in chat.text
    await engine.dispose()

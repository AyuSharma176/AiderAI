import pytest

from app.ai.gateway import AIResponseError, AIUnavailableError, GeminiGateway
from app.ai.types import AnswerRequest, ChatMessage


class FakeTransport:
    intent = {"route": "direct", "tool_name": None, "tool_arguments": {}}
    embedding_vectors = [[1.0, 0.0], [0.0, 1.0]]
    tokens = ["Hello", " world"]
    error: Exception | None = None

    async def classify(self, messages):
        if self.error:
            raise self.error
        return self.intent

    async def embed(self, texts):
        if self.error:
            raise self.error
        return self.embedding_vectors

    async def stream(self, request):
        if self.error:
            raise self.error
        for token in self.tokens:
            yield token


@pytest.mark.asyncio
async def test_embeddings_preserve_input_order() -> None:
    gateway = GeminiGateway(FakeTransport())
    assert await gateway.embed_texts(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]


@pytest.mark.asyncio
async def test_intent_is_validated() -> None:
    transport = FakeTransport()
    transport.intent = {"route": "tool", "tool_name": "get_order_status", "tool_arguments": {"order_id": "ORD-1"}}
    decision = await GeminiGateway(transport).classify_intent([ChatMessage(role="user", content="order?")])
    assert decision.route == "tool"
    assert decision.tool_arguments == {"order_id": "ORD-1"}


@pytest.mark.asyncio
async def test_stream_preserves_provider_tokens() -> None:
    tokens = [token async for token in GeminiGateway(FakeTransport()).stream_answer(AnswerRequest(prompt="hello"))]
    assert tokens == ["Hello", " world"]


@pytest.mark.asyncio
async def test_transport_and_invalid_responses_map_to_safe_errors() -> None:
    unavailable = FakeTransport()
    unavailable.error = TimeoutError("secret upstream detail")
    with pytest.raises(AIUnavailableError, match="AI service is temporarily unavailable"):
        await GeminiGateway(unavailable).embed_texts(["hello"])

    malformed = FakeTransport()
    malformed.intent = {"route": "run_shell"}
    with pytest.raises(AIResponseError, match="AI service returned an invalid response"):
        await GeminiGateway(malformed).classify_intent([])


from collections.abc import AsyncIterator, Sequence
from time import monotonic
from typing import Any, Protocol

import structlog
from pydantic import ValidationError

from app.ai.types import AnswerRequest, ChatMessage, IntentDecision


class AIUnavailableError(RuntimeError):
    pass


class AIResponseError(RuntimeError):
    pass


class ProviderTransport(Protocol):
    async def classify(self, messages: Sequence[ChatMessage]) -> Any: ...
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
    def stream(self, request: AnswerRequest) -> AsyncIterator[str]: ...


class GeminiGateway:
    def __init__(self, transport: ProviderTransport) -> None:
        self.transport = transport

    async def classify_intent(self, messages: Sequence[ChatMessage]) -> IntentDecision:
        started = monotonic()
        try:
            decision = IntentDecision.model_validate(await self.transport.classify(messages))
            structlog.get_logger().info(
                "provider_classification_completed",
                latency_ms=int((monotonic() - started) * 1000),
                route=decision.route,
            )
            return decision
        except ValidationError as exc:
            raise AIResponseError("AI service returned an invalid response") from exc
        except Exception as exc:
            raise AIUnavailableError("AI service is temporarily unavailable") from exc

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            started = monotonic()
            vectors = await self.transport.embed(texts)
        except Exception as exc:
            raise AIUnavailableError("AI service is temporarily unavailable") from exc
        if len(vectors) != len(texts) or any(len(vector) != 768 for vector in vectors):
            raise AIResponseError("AI service returned an invalid response")
        structlog.get_logger().info(
            "provider_embedding_completed",
            latency_ms=int((monotonic() - started) * 1000),
            result_count=len(vectors),
        )
        return vectors

    async def stream_answer(self, request: AnswerRequest) -> AsyncIterator[str]:
        try:
            async for token in self.transport.stream(request):
                if token:
                    yield token
        except Exception as exc:
            raise AIUnavailableError("AI service is temporarily unavailable") from exc


class GoogleGenAITransport:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-3.6-flash",
        embedding_model: str = "gemini-embedding-001",
    ) -> None:
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.embedding_model = embedding_model

    async def classify(self, messages: Sequence[ChatMessage]) -> Any:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents="\n".join(f"{message.role}: {message.content}" for message in messages),
            config={
                "response_mime_type": "application/json",
                "response_schema": IntentDecision,
            },
        )
        return response.parsed

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self.client.aio.models.embed_content(
            model=self.embedding_model,
            contents=list(texts),
            config={"output_dimensionality": 768},
        )
        return [list(item.values) for item in response.embeddings]

    async def stream(self, request: AnswerRequest) -> AsyncIterator[str]:
        async for chunk in await self.client.aio.models.generate_content_stream(
            model=self.model,
            contents=request.prompt,
            config={"system_instruction": request.system_instruction},
        ):
            if chunk.text:
                yield chunk.text

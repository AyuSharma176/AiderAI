import asyncio
from uuid import uuid4

import pytest

from app.agent.graph import AgentDependencies, build_support_graph
from app.ai.types import ChatMessage, ContextChunk, IntentDecision
from app.tools.schemas import ToolResult
from app.tools.support import ToolValidationError


class FakeGateway:
    def __init__(self, intent: IntentDecision) -> None:
        self.intent = intent
        self.requests = []

    async def classify_intent(self, messages):
        return self.intent

    async def stream_answer(self, request):
        self.requests.append(request)
        for token in ("Helpful", " answer"):
            yield token


class FakeRetriever:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def __call__(self, query: str, limit: int):
        self.queries.append(query)
        return [ContextChunk(text="Five days", source="refund.pdf", page=2)]


class FakeTools:
    def __init__(self) -> None:
        self.calls = []

    async def __call__(self, name, arguments, user_id):
        self.calls.append((name, arguments, user_id))
        return ToolResult(name=name, data={"id": str(user_id)})


def base_state(question: str):
    return {
        "messages": [ChatMessage(role="user", content=question)],
        "user_id": uuid4(),
        "events": [],
    }


@pytest.mark.asyncio
async def test_knowledge_route_retrieves_before_generation() -> None:
    gateway = FakeGateway(IntentDecision(route="knowledge"))
    retriever = FakeRetriever()
    graph = build_support_graph(AgentDependencies(gateway, retriever, FakeTools()))

    result = await graph.ainvoke(base_state("What is the refund policy?"))

    assert retriever.queries == ["What is the refund policy?"]
    assert result["citations"][0].source == "refund.pdf"
    assert result["answer"] == "Helpful answer"
    assert [event.type for event in result["events"]] == [
        "stage",
        "stage",
        "citation",
        "stage",
        "token",
        "token",
    ]


@pytest.mark.asyncio
async def test_direct_route_skips_retrieval_and_tools() -> None:
    gateway = FakeGateway(IntentDecision(route="direct"))
    retriever = FakeRetriever()
    tools = FakeTools()
    graph = build_support_graph(AgentDependencies(gateway, retriever, tools))

    await graph.ainvoke(base_state("Hello"))

    assert retriever.queries == []
    assert tools.calls == []


@pytest.mark.asyncio
async def test_tool_route_never_uses_model_user_id() -> None:
    gateway = FakeGateway(
        IntentDecision(
            route="tool",
            tool_name="get_customer_profile",
            tool_arguments={"user_id": "someone-else"},
        )
    )
    tools = FakeTools()
    state = base_state("show profile")
    graph = build_support_graph(AgentDependencies(gateway, FakeRetriever(), tools))

    result = await graph.ainvoke(state)

    assert tools.calls[0][2] == state["user_id"]
    assert result["tool_result"].data["id"] == str(state["user_id"])


@pytest.mark.asyncio
async def test_invalid_tool_arguments_are_not_silently_accepted() -> None:
    gateway = FakeGateway(
        IntentDecision(
            route="tool",
            tool_name="create_support_ticket",
            tool_arguments={"issue": "short"},
        )
    )

    async def invalid_tool(name, arguments, user_id):
        raise ToolValidationError("invalid")

    graph = build_support_graph(AgentDependencies(gateway, FakeRetriever(), invalid_tool))

    with pytest.raises(ToolValidationError):
        await graph.ainvoke(base_state("create a ticket"))


@pytest.mark.asyncio
async def test_token_event_is_emitted_before_generation_completes() -> None:
    release = asyncio.Event()
    emitted = asyncio.Queue()

    class BlockingGateway(FakeGateway):
        async def stream_answer(self, request):
            yield "first"
            await release.wait()
            yield "second"

    graph = build_support_graph(
        AgentDependencies(
            BlockingGateway(IntentDecision(route="direct")),
            FakeRetriever(),
            FakeTools(),
            emit_event=emitted.put,
        )
    )
    execution = asyncio.create_task(graph.ainvoke(base_state("Hello")))
    while True:
        event = await asyncio.wait_for(emitted.get(), timeout=1)
        if event.type == "token":
            break

    assert event.data["text"] == "first"
    assert not execution.done()
    release.set()
    result = await execution
    assert result["answer"] == "firstsecond"

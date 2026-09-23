from collections.abc import Sequence

import structlog

from app.agent.state import AgentDependencies, AgentEvent, ConversationState
from app.ai.prompts import build_answer_prompt
from app.ai.types import ChatMessage


def latest_user_text(messages: Sequence[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    raise ValueError("Conversation requires a user message")


def _append_events(state: ConversationState, *events: AgentEvent) -> list[AgentEvent]:
    return [*state.get("events", []), *events]


async def _emit(dependencies: AgentDependencies, event: AgentEvent) -> None:
    structlog.get_logger().info(
        "agent_event",
        event_type=event.type,
        **{key: value for key, value in event.data.items() if key != "text"},
    )
    if dependencies.emit_event is not None:
        await dependencies.emit_event(event)


def make_analyze_intent(dependencies: AgentDependencies):
    async def analyze_intent(state: ConversationState) -> ConversationState:
        intent = await dependencies.gateway.classify_intent(state["messages"])
        event = AgentEvent(type="stage", data={"name": "analyzing"})
        await _emit(dependencies, event)
        return {
            "intent": intent,
            "events": _append_events(state, event),
        }

    return analyze_intent


def make_retrieve(dependencies: AgentDependencies):
    async def retrieve_context(state: ConversationState) -> ConversationState:
        chunks = await dependencies.retriever(
            latest_user_text(state["messages"]), dependencies.retrieval_top_k
        )
        citation_events = [
            AgentEvent(
                type="citation",
                data={
                    "source": chunk.source,
                    "page": chunk.page,
                    "chunk_id": chunk.chunk_id,
                },
            )
            for chunk in chunks
        ]
        stage = AgentEvent(
            type="stage",
            data={"name": "retrieving", "retrieval_count": len(chunks)},
        )
        await _emit(dependencies, stage)
        for event in citation_events:
            await _emit(dependencies, event)
        return {
            "citations": chunks,
            "events": _append_events(
                state,
                stage,
                *citation_events,
            ),
        }

    return retrieve_context


def make_execute_tool(dependencies: AgentDependencies):
    async def execute_support_tool(state: ConversationState) -> ConversationState:
        intent = state["intent"]
        if intent.tool_name is None:
            raise ValueError("Tool route requires an allow-listed tool name")
        result = await dependencies.execute_tool(
            intent.tool_name,
            intent.tool_arguments,
            state["user_id"],
        )
        event = AgentEvent(type="stage", data={"name": "using_tool", "tool": intent.tool_name})
        await _emit(dependencies, event)
        return {
            "tool_result": result,
            "events": _append_events(
                state,
                event,
            ),
        }

    return execute_support_tool


def make_generate_response(dependencies: AgentDependencies):
    async def generate_response(state: ConversationState) -> ConversationState:
        question = latest_user_text(state["messages"])
        tool_result = state.get("tool_result")
        request = build_answer_prompt(
            question,
            state.get("citations", []),
            state["messages"],
            tool_result.model_dump(mode="json", exclude_none=True) if tool_result else None,
        )
        tokens: list[str] = []
        stage = AgentEvent(type="stage", data={"name": "generating"})
        await _emit(dependencies, stage)
        events = _append_events(state, stage)
        async for token in dependencies.gateway.stream_answer(request):
            tokens.append(token)
            event = AgentEvent(type="token", data={"text": token})
            events.append(event)
            await _emit(dependencies, event)
        return {"answer": "".join(tokens), "events": events}

    return generate_response


def route_after_intent(state: ConversationState) -> str:
    return state["intent"].route

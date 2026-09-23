from collections.abc import Sequence

from app.agent.state import AgentDependencies, AgentEvent, ConversationState
from app.ai.prompts import build_answer_prompt
from app.ai.types import AnswerRequest, ChatMessage


def latest_user_text(messages: Sequence[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    raise ValueError("Conversation requires a user message")


def _append_events(
    state: ConversationState, *events: AgentEvent
) -> list[AgentEvent]:
    return [*state.get("events", []), *events]


def make_analyze_intent(dependencies: AgentDependencies):
    async def analyze_intent(state: ConversationState) -> ConversationState:
        intent = await dependencies.gateway.classify_intent(state["messages"])
        return {
            "intent": intent,
            "events": _append_events(
                state, AgentEvent(type="stage", data={"name": "analyzing"})
            ),
        }

    return analyze_intent


def make_retrieve(dependencies: AgentDependencies):
    async def retrieve_context(state: ConversationState) -> ConversationState:
        chunks = await dependencies.retriever(latest_user_text(state["messages"]), 5)
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
        return {
            "citations": chunks,
            "events": _append_events(
                state,
                AgentEvent(type="stage", data={"name": "retrieving"}),
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
        return {
            "tool_result": result,
            "events": _append_events(
                state,
                AgentEvent(
                    type="stage",
                    data={"name": "using_tool", "tool": intent.tool_name},
                ),
            ),
        }

    return execute_support_tool


def make_generate_response(dependencies: AgentDependencies):
    async def generate_response(state: ConversationState) -> ConversationState:
        question = latest_user_text(state["messages"])
        prompt = build_answer_prompt(question, state.get("citations", []))
        if tool_result := state.get("tool_result"):
            prompt += (
                "\n\nTRUSTED_TOOL_RESULT:\n"
                + tool_result.model_dump_json(exclude_none=True)
            )
        tokens: list[str] = []
        events = _append_events(
            state, AgentEvent(type="stage", data={"name": "generating"})
        )
        async for token in dependencies.gateway.stream_answer(AnswerRequest(prompt=prompt)):
            tokens.append(token)
            events.append(AgentEvent(type="token", data={"text": token}))
        return {"answer": "".join(tokens), "events": events}

    return generate_response


def route_after_intent(state: ConversationState) -> str:
    return state["intent"].route

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    make_analyze_intent,
    make_execute_tool,
    make_generate_response,
    make_retrieve,
    route_after_intent,
)
from app.agent.state import AgentDependencies, ConversationState

__all__ = ["AgentDependencies", "ConversationState", "build_support_graph"]


def build_support_graph(dependencies: AgentDependencies):
    graph = StateGraph(ConversationState)
    graph.add_node("analyze_intent", make_analyze_intent(dependencies))
    graph.add_node("retrieve", make_retrieve(dependencies))
    graph.add_node("execute_tool", make_execute_tool(dependencies))
    graph.add_node("generate_response", make_generate_response(dependencies))
    graph.add_edge(START, "analyze_intent")
    graph.add_conditional_edges(
        "analyze_intent",
        route_after_intent,
        {
            "knowledge": "retrieve",
            "tool": "execute_tool",
            "direct": "generate_response",
        },
    )
    graph.add_edge("retrieve", "generate_response")
    graph.add_edge("execute_tool", "generate_response")
    graph.add_edge("generate_response", END)
    return graph.compile()

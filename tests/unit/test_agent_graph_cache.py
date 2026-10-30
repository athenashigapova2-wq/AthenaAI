"""Checks for process-wide LangGraph compilation caching."""

from unittest.mock import patch

from app.agents import graph as agent_graph
from langchain_core.messages import AIMessage


def test_get_agent_graph_compiles_once() -> None:
    compiled_graph = object()
    agent_graph.get_agent_graph.cache_clear()
    try:
        with patch.object(
            agent_graph,
            "build_agent_graph",
            return_value=compiled_graph,
        ) as build:
            assert agent_graph.get_agent_graph() is compiled_graph
            assert agent_graph.get_agent_graph() is compiled_graph

        build.assert_called_once_with()
    finally:
        agent_graph.get_agent_graph.cache_clear()


def test_public_graph_result_sanitizes_textual_tool_markers() -> None:
    class FakeGraph:
        @staticmethod
        def invoke(_state):
            return {
                "messages": [
                    AIMessage(
                        content=(
                            '[GET_GETMYPROFILE, SEARCH_SEARCHFOOD "запеканка"] '
                            "Приготовьте запеканку."
                        )
                    )
                ],
                "route": "nutrition",
                "resolution_mode": "main_llm",
            }

    with patch.object(agent_graph, "get_agent_graph", return_value=FakeGraph()):
        result = agent_graph.run_agent_turn_details("user-id", "Что приготовить?", "ru")

    assert result["answer"] == "Приготовьте запеканку."

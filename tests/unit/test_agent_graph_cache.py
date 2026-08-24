"""Checks for process-wide LangGraph compilation caching."""

from unittest.mock import patch

from app.agents import graph as agent_graph


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

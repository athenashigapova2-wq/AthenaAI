"""Offline checks for the explicit deterministic mock LLM mode."""

import sys
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, settings  # noqa: E402
from app.agents.graph import run_agent_turn_details  # noqa: E402
from app.ai_execution import ai_execution_service  # noqa: E402
from app.llm import _get_mock_llm  # noqa: E402
from app.mock_llm import AthenaMockChatModel  # noqa: E402
from app.services import agent_traces  # noqa: E402


def check_configuration_is_explicit() -> None:
    assert Settings(_env_file=None).llm_provider == "gigachat"
    try:
        Settings(_env_file=None, llm_provider="unknown")
    except ValidationError:
        pass
    else:
        raise AssertionError("Unknown LLM provider was accepted")


def check_mock_routing_and_answers() -> None:
    _get_mock_llm.cache_clear()
    with (
        patch.object(settings, "llm_provider", "mock"),
        patch.object(settings, "mock_llm_model", "athena-mock-test"),
        patch.object(settings, "mock_llm_latency_ms", 0),
    ):
        router_prepared = ai_execution_service.prepare(
            node_name="router",
            purpose="route_classification",
            default_tier="small",
        )
        router = router_prepared.model
        selection = router_prepared.selection
        assert isinstance(router, AthenaMockChatModel)
        assert selection.provider == "mock"
        assert selection.model_name == "athena-mock-test"
        assert selection.is_fallback is False
        route = router.invoke([HumanMessage(content="Сколько белка мне нужно?")])
        assert route.content == '{"route":"nutrition"}'

        specialist_prepared = ai_execution_service.prepare(
            node_name="nutrition",
            purpose="tool_planning_or_answer",
        )
        specialist = specialist_prepared.model
        specialist_selection = specialist_prepared.selection
        bound = specialist.bind_tools(
            [{"type": "function", "function": {"name": "get_my_profile"}}]
        )
        answer = bound.invoke(
            [
                SystemMessage(
                    content="The user's language is Russian. Reply only in Russian."
                ),
                HumanMessage(content="Помоги с питанием"),
            ]
        )
        assert answer.content.startswith("[MOCK:nutrition]")
        assert answer.tool_calls == []
        assert specialist_selection.provider == "mock"


def check_mock_bypasses_gigachat_circuit_breaker() -> None:
    model = AthenaMockChatModel(node_name="general", purpose="answer")
    with (
        patch.object(settings, "llm_provider", "mock"),
        patch(
            "app.ai_execution.gateway.call_with_circuit_breaker"
        ) as circuit_breaker,
    ):
        response = agent_traces.invoke_llm(
            model,
            [HumanMessage(content="Привет")],
            run_id=None,
            node_name="general",
            purpose="answer",
            model_tier="main",
        )
    assert response.content.startswith("[MOCK:general]")
    circuit_breaker.assert_not_called()


def check_full_agent_graph() -> None:
    _get_mock_llm.cache_clear()
    with (
        patch.object(settings, "llm_provider", "mock"),
        patch.object(settings, "mock_llm_model", "athena-mock-test"),
        patch.object(settings, "mock_llm_latency_ms", 0),
        patch.object(settings, "rag_enabled", False),
    ):
        result = run_agent_turn_details(
            "00000000-0000-0000-0000-000000000000",
            "Сколько белка мне нужно?",
            "ru",
        )
    assert result["route"] == "nutrition"
    assert result["answer"].startswith("[MOCK:nutrition]")


if __name__ == "__main__":
    check_configuration_is_explicit()
    check_mock_routing_and_answers()
    check_mock_bypasses_gigachat_circuit_breaker()
    check_full_agent_graph()
    print("Mock LLM checks passed")

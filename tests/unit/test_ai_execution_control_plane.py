"""Contracts for the canonical Python LLM control plane."""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.ai_execution import AIExecutionService
from app.config import settings


class RecordingGateway:
    def __init__(self) -> None:
        self.model = object()
        self.messages = []

    def model_for(self, **kwargs):
        return self.model

    def invoke(self, model, messages):
        assert model is self.model
        self.messages = messages
        return AIMessage(content="ok")


def test_control_plane_routes_sanitizes_and_invokes(monkeypatch) -> None:
    gateway = RecordingGateway()
    service = AIExecutionService(gateway=gateway)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "mock_llm_model", "athena-mock-control-plane")

    response = service.invoke(
        messages=[
            HumanMessage(
                content="weight=72.5 authorization=Bearer private-credential"
            )
        ],
        node_name="nutrition",
        purpose="answer",
    )

    assert response.content == "ok"
    outbound = str(gateway.messages[0].content)
    assert "weight=72.5" in outbound
    assert "private-credential" not in outbound


def test_control_plane_owns_llm_trace_lifecycle(monkeypatch) -> None:
    gateway = RecordingGateway()
    service = AIExecutionService(gateway=gateway)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "mock_llm_model", "athena-mock-control-plane")

    with (
        patch(
            "app.ai_execution.gateway.agent_traces.create_llm_call",
            return_value="llm-call-id",
        ) as create_trace,
        patch("app.ai_execution.gateway.agent_traces.succeed_llm_call") as succeed_trace,
    ):
        service.invoke(
            messages=[HumanMessage(content="hello")],
            node_name="general",
            purpose="answer",
            run_id="run-id",
        )

    create_trace.assert_called_once()
    assert create_trace.call_args.args[:4] == (
        "run-id",
        "general",
        "answer",
        "main",
    )
    succeed_trace.assert_called_once()


def test_provider_failure_is_traced_and_propagated(monkeypatch) -> None:
    gateway = RecordingGateway()

    def fail(model, messages):
        raise ValueError("provider rejected request")

    gateway.invoke = fail
    service = AIExecutionService(gateway=gateway)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "mock_llm_model", "athena-mock-control-plane")

    with (
        patch(
            "app.ai_execution.gateway.agent_traces.create_llm_call",
            return_value="llm-call-id",
        ),
        patch("app.ai_execution.gateway.agent_traces.fail_llm_call") as fail_trace,
        pytest.raises(ValueError, match="provider rejected"),
    ):
        service.invoke(
            messages=[HumanMessage(content="hello")],
            node_name="general",
            purpose="answer",
            run_id="run-id",
        )

    fail_trace.assert_called_once()

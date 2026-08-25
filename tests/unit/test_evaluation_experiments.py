"""Deterministic contracts for server-owned evaluation experiments."""

from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from app.ai_execution import AIExecutionService
from app.evaluation.experiments import (
    ExperimentDefinition,
    ExperimentVariant,
    assign_experiment,
    current_experiment,
    experiment_context,
)


def _definition() -> ExperimentDefinition:
    return ExperimentDefinition(
        experiment_id="quality-v1",
        salt="stable-test-salt-at-least-16",
        enabled=True,
        allocation_percent=100,
        variants=[
            ExperimentVariant(variant_id="control", weight=50),
            ExperimentVariant(
                variant_id="small",
                weight=50,
                model_tier="small",
                temperature=0.1,
                input_cost_per_million_usd=2.0,
                output_cost_per_million_usd=4.0,
            ),
        ],
    )


def test_assignment_is_stable_and_auditable() -> None:
    definition = _definition()
    first = assign_experiment(definition, "user-123")
    second = assign_experiment(definition, "user-123")

    assert first == second
    assert first is not None
    assert first.config_hash == definition.config_hash()
    assert 0 <= first.assignment_bucket < 10_000


def test_assignment_context_is_process_local_and_resets() -> None:
    assignment = assign_experiment(_definition(), "user-123")
    assert current_experiment() is None
    with experiment_context(assignment):
        assert current_experiment() == assignment
    assert current_experiment() is None


def test_pricing_uses_measured_tokens_and_never_guesses() -> None:
    priced = ExperimentVariant(
        variant_id="priced",
        weight=1,
        input_cost_per_million_usd=2,
        output_cost_per_million_usd=4,
    )
    unpriced = ExperimentVariant(variant_id="unpriced", weight=1)
    definition = ExperimentDefinition(
        experiment_id="cost-v1",
        salt="stable-cost-test-salt",
        enabled=True,
        variants=[priced, unpriced],
    )
    assignment = assign_experiment(definition, "find-a-priced-user")
    if assignment is None or assignment.variant_id != "priced":
        assignment = next(
            candidate
            for index in range(1_000)
            if (candidate := assign_experiment(definition, f"user-{index}")) is not None
            and candidate.variant_id == "priced"
        )

    assert assignment.estimated_cost_usd(1_000, 500) == 0.004


class _Gateway:
    def __init__(self) -> None:
        self.selection = None
        self.temperature = None

    def model_for(self, *, selection, temperature, **_):
        self.selection = selection
        self.temperature = temperature
        return object()

    @staticmethod
    def invoke(model, messages):
        return AIMessage(content="ok")


def test_variant_can_override_server_model_policy(monkeypatch) -> None:
    gateway = _Gateway()
    service = AIExecutionService(gateway=gateway)
    definition = ExperimentDefinition(
        experiment_id="routing-v1",
        salt="stable-routing-test-salt",
        enabled=True,
        variants=[
            ExperimentVariant(variant_id="control", weight=1),
            ExperimentVariant(
                variant_id="forced-small",
                weight=1,
                model_tier="small",
                temperature=0.2,
            ),
        ],
    )
    assignment = next(
        candidate
        for index in range(1_000)
        if (candidate := assign_experiment(definition, f"actor-{index}")) is not None
        and candidate.variant_id == "forced-small"
    )
    monkeypatch.setattr("app.model_routing.settings.llm_provider", "mock")
    monkeypatch.setattr("app.model_routing.settings.mock_llm_model", "mock-model")

    with (
        experiment_context(assignment),
        patch("app.ai_execution.gateway.agent_traces.create_llm_call", return_value="call"),
        patch("app.ai_execution.gateway.agent_traces.succeed_llm_call"),
    ):
        service.invoke(
            messages=[HumanMessage(content="hello")],
            node_name="general",
            purpose="answer",
            run_id="trace-id",
        )

    assert gateway.selection.requested_model_tier == "small"
    assert gateway.selection.matched_rule == "evaluation_experiment"
    assert gateway.temperature == 0.2

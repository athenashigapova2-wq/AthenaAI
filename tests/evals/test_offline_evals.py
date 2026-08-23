"""Deterministic evals that never call a model provider or remote tool."""

import pytest

from scripts import eval_agents, eval_tool_selection, eval_write_safety


pytestmark = pytest.mark.eval


def test_agent_routing_dataset() -> None:
    cases = eval_agents.load_cases()
    accuracy, failures = eval_agents.evaluate(cases)
    assert failures == []
    assert accuracy == 1.0


@pytest.mark.parametrize(
    ("load_cases", "validate_cases"),
    (
        (eval_tool_selection.load_cases, eval_tool_selection.validate_cases),
        (eval_write_safety.load_cases, eval_tool_selection.validate_cases),
    ),
    ids=("tool-selection", "write-safety"),
)
def test_eval_dataset_contract(load_cases, validate_cases) -> None:
    cases = load_cases()
    assert cases
    assert validate_cases(cases) == []


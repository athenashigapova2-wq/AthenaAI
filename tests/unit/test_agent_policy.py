"""Core routing, tool-boundary, and nutrition safety checks."""

import pytest
from unittest.mock import patch

from app.config import settings
from scripts import test_agent_architecture as architecture_checks
from scripts import test_model_routing as routing_checks
from scripts import test_nutrition_guardrails as nutrition_checks


pytestmark = pytest.mark.unit


def _run_with_gigachat_policy(check) -> None:
    # The developer .env may intentionally select the infrastructure mock.
    # Routing policy checks model GigaChat tier selection and must not inherit it.
    with patch.object(settings, "llm_provider", "gigachat"):
        check()


@pytest.mark.parametrize(
    "check",
    (
        architecture_checks.assert_routes,
        architecture_checks.assert_tool_boundaries,
    ),
    ids=lambda check: check.__name__,
)
def test_tool_access_boundaries(check) -> None:
    _run_with_gigachat_policy(check)


@pytest.mark.parametrize(
    "check",
    (
        routing_checks.check_rule_precedence,
        routing_checks.check_disabled_policy_uses_call_default,
        routing_checks.check_small_tier_falls_back_to_main_model,
        routing_checks.check_routed_client_uses_selected_model,
        routing_checks.check_invalid_policy_is_rejected,
        routing_checks.check_policy_json_is_loaded_from_environment,
    ),
    ids=lambda check: check.__name__,
)
def test_routing_policy(check) -> None:
    _run_with_gigachat_policy(check)


@pytest.mark.parametrize(
    "check",
    (
        nutrition_checks.check_intent_detection,
        nutrition_checks.check_programmatic_totals,
        nutrition_checks.check_food_lookup_never_substitutes_a_different_food,
        nutrition_checks.check_weight_trend_is_forced,
        nutrition_checks.check_tool_call_keys_are_normalized_before_validation,
        nutrition_checks.check_household_portions_and_food_diversity,
        nutrition_checks.check_progress_request_forces_weight_trend_in_recovery,
        nutrition_checks.check_invalid_draft_is_fitted_before_return,
    ),
    ids=lambda check: check.__name__,
)
def test_nutrition_invariants_and_safety(check) -> None:
    _run_with_gigachat_policy(check)

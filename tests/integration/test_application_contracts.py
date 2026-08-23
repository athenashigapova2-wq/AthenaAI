"""In-process contracts across FastAPI, Celery, the agent graph, and observability."""

import pytest
from unittest.mock import patch

from app.config import settings
from scripts import test_agent_workers as worker_checks
from scripts import test_fastapi as api_checks
from scripts import test_jmeter_observability as observability_checks
from scripts import test_load_tests as load_checks
from scripts import test_mock_llm as mock_checks


pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "check",
    (
        api_checks.check_jwt_boundary,
        api_checks.check_job_api,
        api_checks.check_readiness_respects_llm_provider,
        worker_checks.check_agent_service,
        worker_checks.check_worker_task,
        worker_checks.check_job_ownership,
        mock_checks.check_configuration_is_explicit,
        mock_checks.check_mock_routing_and_answers,
        mock_checks.check_mock_bypasses_gigachat_circuit_breaker,
        mock_checks.check_full_agent_graph,
        observability_checks.check_jmeter_plan,
        observability_checks.check_grafana_dashboard,
        load_checks.check_stages,
        load_checks.check_settings_guard,
        load_checks.check_token_pool,
        load_checks.check_slo_analysis,
    ),
    ids=lambda check: check.__name__,
)
def test_application_contract(check) -> None:
    if check is api_checks.check_job_api:
        with (
            patch.object(settings, "supabase_jwt_secret", api_checks.TEST_JWT_SECRET),
            patch.object(settings, "supabase_url", "https://project.supabase.co"),
        ):
            check()
        return

    if check is worker_checks.check_worker_task:
        with patch.object(settings, "agent_infrastructure_test_mode", False):
            check()
        return

    check()

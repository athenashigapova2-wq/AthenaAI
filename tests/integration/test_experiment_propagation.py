"""HTTP-to-Celery propagation for server-owned experiment assignments."""

from unittest.mock import patch

import pytest

from app.config import settings
from app.evaluation.experiments import ExperimentAssignment, current_experiment
from app.workers.tasks import run_agent_chat_task
from scripts import test_fastapi as api_checks


pytestmark = pytest.mark.integration


def _assignment() -> ExperimentAssignment:
    return ExperimentAssignment(
        experiment_id="quality-v1",
        variant_id="small",
        assignment_bucket=1234,
        config_hash="a" * 64,
        model_tier="small",
    )


def test_http_assigns_experiment_server_side_and_enqueues_it() -> None:
    assignment = _assignment()
    with (
        patch.object(settings, "supabase_jwt_secret", api_checks.TEST_JWT_SECRET),
        patch.object(settings, "supabase_url", "https://project.supabase.co"),
        patch("app.api.agent.assign_active_experiment", return_value=assignment),
        patch("app.api.agent.uuid4", return_value=api_checks.TRACE_ID),
        patch(
            "app.api.agent.agent_jobs.enqueue_agent_job",
            return_value=api_checks.JOB_ID,
        ) as enqueue,
    ):
        response = api_checks.client.post(
            "/api/v1/agent/chat",
            headers=api_checks.auth_headers(),
            json={"message": "Hello", "locale": "en"},
        )

    assert response.status_code == 202
    assert response.json()["experiment_id"] == "quality-v1"
    assert response.json()["variant_id"] == "small"
    assert enqueue.call_args.kwargs["trace_id"] == api_checks.TRACE_ID
    assert enqueue.call_args.kwargs["experiment_id"] == "quality-v1"
    assert enqueue.call_args.kwargs["variant_id"] == "small"


def test_client_cannot_select_its_experiment_variant() -> None:
    with (
        patch.object(settings, "supabase_jwt_secret", api_checks.TEST_JWT_SECRET),
        patch.object(settings, "supabase_url", "https://project.supabase.co"),
    ):
        response = api_checks.client.post(
            "/api/v1/agent/chat",
            headers=api_checks.auth_headers(),
            json={
                "message": "Hello",
                "experiment_id": "quality-v1",
                "variant_id": "preferred",
            },
        )

    assert response.status_code == 422


def test_celery_verifies_assignment_and_binds_it_to_execution_context() -> None:
    assignment = _assignment()
    result = {"answer": "Done", "route": "general", "conversation_id": "conversation"}

    def run_agent(**kwargs):
        assert current_experiment() == assignment
        assert kwargs["trace_id"] == "trace-id"
        assert kwargs["experiment_id"] == "quality-v1"
        assert kwargs["variant_id"] == "small"
        return result

    with (
        patch.object(settings, "agent_infrastructure_test_mode", False),
        patch("app.workers.tasks.resolve_assignment", return_value=assignment) as resolve,
        patch("app.workers.tasks.raise_if_current_job_cancelled"),
        patch("app.workers.tasks.mark_job_running", return_value=17),
        patch("app.workers.tasks.run_agent_chat", side_effect=run_agent),
        patch("app.workers.tasks.mark_job_succeeded"),
    ):
        run_agent_chat_task.run(
            job_id="job-id",
            user_id="user-id",
            message="Hello",
            locale="en",
            conversation_id=None,
            trace_id="trace-id",
            experiment_id="quality-v1",
            variant_id="small",
        )

    resolve.assert_called_once_with(
        actor_id="user-id",
        experiment_id="quality-v1",
        variant_id="small",
    )
    assert current_experiment() is None

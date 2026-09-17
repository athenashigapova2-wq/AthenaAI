from unittest.mock import MagicMock, patch

import pytest
from app.services import agent_jobs
from app.services.agent_jobs import (
    AgentJobCancelledError,
    QueueUnavailableError,
    enqueue_agent_job,
)
from redis.exceptions import RedisError


def _redis_client() -> MagicMock:
    client = MagicMock()
    client.pipeline.return_value.__enter__.return_value = MagicMock()
    return client


def _enqueue() -> str:
    return enqueue_agent_job(
        user_id="user-1",
        message="hello",
        locale="en",
        conversation_id=None,
        trace_id="trace-1",
    )


def test_enqueue_keeps_accepted_job_when_queued_event_publish_fails() -> None:
    client = _redis_client()
    with (
        patch("app.services.agent_jobs.redis_client", return_value=client),
        patch("app.workers.tasks.run_agent_chat_task.apply_async") as apply_async,
        patch(
            "app.services.agent_jobs._publish_event",
            side_effect=RedisError("pubsub unavailable"),
        ),
    ):
        job_id = _enqueue()

    assert job_id
    apply_async.assert_called_once()
    client.delete.assert_not_called()


def test_enqueue_removes_job_record_when_broker_submission_fails() -> None:
    client = _redis_client()
    with (
        patch("app.services.agent_jobs.redis_client", return_value=client),
        patch(
            "app.workers.tasks.run_agent_chat_task.apply_async",
            side_effect=RuntimeError("broker unavailable"),
        ),
        pytest.raises(QueueUnavailableError),
    ):
        _enqueue()

    client.delete.assert_called_once()


def test_worker_update_cannot_overwrite_cancelled_job() -> None:
    client = MagicMock()
    client.eval.return_value = 0

    with (
        patch("app.services.agent_jobs.redis_client", return_value=client),
        pytest.raises(AgentJobCancelledError),
    ):
        agent_jobs.mark_job_succeeded("job-1", {"answer": "late result"})

    client.eval.assert_called_once()
    assert client.eval.call_args.args[0] == agent_jobs._UPDATE_JOB_SCRIPT
    assert client.eval.call_args.args[3] == "succeeded"


def test_worker_update_cannot_recreate_expired_job() -> None:
    client = MagicMock()
    client.eval.return_value = 0

    with (
        patch("app.services.agent_jobs.redis_client", return_value=client),
        pytest.raises(AgentJobCancelledError),
    ):
        agent_jobs.mark_job_failed("expired-job", "late failure")

    client.hset.assert_not_called()


def test_cancel_atomically_transitions_owned_active_job() -> None:
    client = MagicMock()
    client.eval.return_value = 1
    client.hgetall.return_value = {
        "user_id": "user-1",
        "status": "cancelled",
        "stage": "cancelled",
        "trace_id": "trace-1",
    }

    with (
        patch("app.services.agent_jobs.redis_client", return_value=client),
        patch("app.services.agent_jobs._publish_event") as publish_event,
        patch("app.workers.celery_app.celery_app.control.revoke") as revoke,
    ):
        result = agent_jobs.cancel_agent_job("job-1", "user-1")

    assert result is not None
    assert result["status"] == "cancelled"
    assert client.eval.call_args.args[0] == agent_jobs._CANCEL_JOB_SCRIPT
    publish_event.assert_called_once_with("job-1", "cancelled")
    revoke.assert_called_once_with("job-1", terminate=False)


def test_cancel_does_not_overwrite_job_that_completed_first() -> None:
    client = MagicMock()
    client.eval.return_value = 0
    client.hgetall.return_value = {
        "user_id": "user-1",
        "status": "succeeded",
        "stage": "completed",
        "trace_id": "trace-1",
        "result": '{"answer": "finished"}',
    }

    with (
        patch("app.services.agent_jobs.redis_client", return_value=client),
        patch("app.services.agent_jobs._publish_event") as publish_event,
        patch("app.workers.celery_app.celery_app.control.revoke") as revoke,
    ):
        result = agent_jobs.cancel_agent_job("job-1", "user-1")

    assert result is not None
    assert result["status"] == "succeeded"
    assert result["answer"] == "finished"
    publish_event.assert_not_called()
    revoke.assert_not_called()


def test_cancel_hides_missing_and_foreign_jobs() -> None:
    client = MagicMock()
    client.eval.return_value = -1

    with patch("app.services.agent_jobs.redis_client", return_value=client):
        result = agent_jobs.cancel_agent_job("job-1", "other-user")

    assert result is None

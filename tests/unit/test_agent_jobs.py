from unittest.mock import MagicMock, patch

import pytest
from app.services.agent_jobs import QueueUnavailableError, enqueue_agent_job
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

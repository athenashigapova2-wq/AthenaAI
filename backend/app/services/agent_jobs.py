"""Redis persistence and Celery submission for authenticated agent jobs."""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterator
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from app.config import settings

JOB_KEY_PREFIX = "athena:agent-job:"
JOB_EVENT_CHANNEL_PREFIX = "athena:agent-job-events:"
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
_current_job_id: ContextVar[str | None] = ContextVar("agent_job_id", default=None)


class QueueUnavailableError(Exception):
    """Redis or the Celery broker could not accept a job."""


class AgentJobCancelledError(Exception):
    """The authenticated caller requested cancellation of the current job."""


@lru_cache(maxsize=1)
def redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )


def _job_key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}{job_id}"


def job_event_channel(job_id: str) -> str:
    return f"{JOB_EVENT_CHANNEL_PREFIX}{job_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redis_is_ready() -> bool:
    try:
        return bool(redis_client().ping())
    except RedisError:
        return False


def enqueue_agent_job(
    *,
    user_id: str,
    message: str,
    locale: str,
    conversation_id: str | None,
    trace_id: str,
) -> str:
    """Create an owner-scoped Redis record, then enqueue the Celery task."""
    # Imported lazily so service and API unit tests do not need to initialize Celery.
    from app.workers.tasks import run_agent_chat_task

    job_id = str(uuid4())
    key = _job_key(job_id)
    client = redis_client()
    enqueued_at = _now()
    try:
        with client.pipeline() as pipe:
            pipe.hset(
                key,
                mapping={
                    "user_id": user_id,
                    "trace_id": trace_id,
                    "status": "queued",
                    "stage": "queued",
                    "created_at": enqueued_at,
                    "updated_at": enqueued_at,
                },
            )
            pipe.expire(key, settings.agent_job_ttl_seconds)
            pipe.execute()
        run_agent_chat_task.apply_async(
            kwargs={
                "job_id": job_id,
                "user_id": user_id,
                "message": message,
                "locale": locale,
                "conversation_id": conversation_id,
                "trace_id": trace_id,
            },
            task_id=job_id,
            queue=settings.agent_job_queue,
        )
        _publish_event(job_id, "queued")
    except Exception as exc:
        try:
            client.delete(key)
        except RedisError:
            pass
        raise QueueUnavailableError("Redis job queue is unavailable") from exc
    return job_id


def get_agent_job(job_id: str, user_id: str) -> dict[str, Any] | None:
    try:
        record = redis_client().hgetall(_job_key(job_id))
    except RedisError as exc:
        raise QueueUnavailableError("Redis job store is unavailable") from exc
    # Return the same response for missing and foreign jobs to avoid leaking IDs.
    if not record or record.get("user_id") != user_id:
        return None

    status = record["status"]
    fallback_stage = "completed" if status == "succeeded" else status
    response: dict[str, Any] = {
        "job_id": job_id,
        # Compatibility for jobs accepted before trace propagation was deployed.
        "trace_id": record.get("trace_id") or job_id,
        "status": status,
        "stage": record.get("stage") or fallback_stage,
    }
    if record.get("result"):
        response.update(json.loads(record["result"]))
    if record.get("error"):
        response["error"] = record["error"]
    return response


def mark_job_running(job_id: str) -> int:
    """Mark worker start and return HTTP-to-worker queue latency."""
    created_at = redis_client().hget(_job_key(job_id), "created_at")
    queue_latency_ms = 0
    if created_at:
        queued = datetime.fromisoformat(created_at)
        queue_latency_ms = max(
            0,
            round((datetime.now(timezone.utc) - queued).total_seconds() * 1_000),
        )
    _update_job(
        job_id,
        status="running",
        stage="running",
        queue_latency_ms=str(queue_latency_ms),
        event="running",
        event_details={"queue_latency_ms": queue_latency_ms},
    )
    return queue_latency_ms


def mark_job_progress(job_id: str, stage: str, **details: Any) -> None:
    if stage not in {"running", "tool_call", "generating"}:
        raise ValueError(f"Unsupported agent job stage: {stage}")
    fields = {"status": "running", "stage": stage}
    _update_job(job_id, event=stage, event_details=details, **fields)


def mark_job_succeeded(job_id: str, result: dict[str, Any]) -> None:
    _update_job(
        job_id,
        status="succeeded",
        stage="completed",
        result=json.dumps(result, ensure_ascii=False),
        event="completed",
    )


def mark_job_failed(job_id: str, error: str) -> None:
    _update_job(job_id, status="failed", stage="failed", error=error, event="failed")


def cancel_agent_job(job_id: str, user_id: str) -> dict[str, Any] | None:
    """Owner-scope a cancellation, persist it, publish it and revoke queued work."""
    client = redis_client()
    key = _job_key(job_id)
    try:
        record = client.hgetall(key)
        if not record or record.get("user_id") != user_id:
            return None
        if record.get("status") not in TERMINAL_STATUSES:
            _update_job(
                job_id,
                status="cancelled",
                stage="cancelled",
                cancel_requested="1",
                event="cancelled",
            )
            from app.workers.celery_app import celery_app

            try:
                celery_app.control.revoke(job_id, terminate=False)
            except Exception:
                # Redis cancellation remains authoritative; revoke is only an
                # optimization for tasks that have not been consumed yet.
                pass
        return get_agent_job(job_id, user_id)
    except RedisError as exc:
        raise QueueUnavailableError("Redis job store is unavailable") from exc


def job_is_cancelled(job_id: str) -> bool:
    try:
        record = redis_client().hmget(_job_key(job_id), "status", "cancel_requested")
    except RedisError as exc:
        raise QueueUnavailableError("Redis job store is unavailable") from exc
    return record[0] == "cancelled" or record[1] == "1"


@contextmanager
def agent_job_context(job_id: str) -> Iterator[None]:
    token = _current_job_id.set(job_id)
    try:
        yield
    finally:
        _current_job_id.reset(token)


def publish_current_job_progress(stage: str, **details: Any) -> None:
    job_id = _current_job_id.get()
    if job_id is not None:
        raise_if_current_job_cancelled()
        mark_job_progress(job_id, stage, **details)


def raise_if_current_job_cancelled() -> None:
    job_id = _current_job_id.get()
    if job_id is not None and job_is_cancelled(job_id):
        raise AgentJobCancelledError("Agent job was cancelled")


def _publish_event(job_id: str, event: str, details: dict[str, Any] | None = None) -> None:
    job = redis_client().hgetall(_job_key(job_id))
    payload: dict[str, Any] = {
        "job_id": job_id,
        "trace_id": job.get("trace_id") or job_id,
        "status": job.get("status", event),
        "stage": job.get("stage", event),
    }
    if details:
        payload.update(details)
    if job.get("result") and event == "completed":
        payload.update(json.loads(job["result"]))
    if job.get("error"):
        payload["error"] = job["error"]
    redis_client().publish(
        job_event_channel(job_id),
        json.dumps({"event": event, "data": payload}, ensure_ascii=False),
    )


def _update_job(
    job_id: str,
    *,
    event: str | None = None,
    event_details: dict[str, Any] | None = None,
    **fields: str,
) -> None:
    fields["updated_at"] = _now()
    key = _job_key(job_id)
    client = redis_client()
    current_status = client.hget(key, "status")
    if current_status == "cancelled" and fields.get("status") != "cancelled":
        raise AgentJobCancelledError("Agent job was cancelled")
    with client.pipeline() as pipe:
        pipe.hset(key, mapping=fields)
        pipe.expire(key, settings.agent_job_ttl_seconds)
        pipe.execute()
    if event is not None:
        _publish_event(job_id, event, event_details)

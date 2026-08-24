"""Redis persistence and Celery submission for authenticated agent jobs."""

import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from app.config import settings

JOB_KEY_PREFIX = "athena:agent-job:"


class QueueUnavailableError(Exception):
    """Redis or the Celery broker could not accept a job."""


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
) -> str:
    """Create an owner-scoped Redis record, then enqueue the Celery task."""
    # Imported lazily so service and API unit tests do not need to initialize Celery.
    from app.workers.tasks import run_agent_chat_task

    job_id = str(uuid4())
    key = _job_key(job_id)
    client = redis_client()
    try:
        with client.pipeline() as pipe:
            pipe.hset(
                key,
                mapping={
                    "user_id": user_id,
                    "status": "queued",
                    "created_at": _now(),
                    "updated_at": _now(),
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
            },
            task_id=job_id,
            queue=settings.agent_job_queue,
        )
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

    response: dict[str, Any] = {
        "job_id": job_id,
        "status": record["status"],
    }
    if record.get("result"):
        response.update(json.loads(record["result"]))
    if record.get("error"):
        response["error"] = record["error"]
    return response


def mark_job_running(job_id: str) -> None:
    _update_job(job_id, status="running")


def mark_job_succeeded(job_id: str, result: dict[str, Any]) -> None:
    _update_job(job_id, status="succeeded", result=json.dumps(result, ensure_ascii=False))


def mark_job_failed(job_id: str, error: str) -> None:
    _update_job(job_id, status="failed", error=error)


def _update_job(job_id: str, **fields: str) -> None:
    fields["updated_at"] = _now()
    key = _job_key(job_id)
    client = redis_client()
    with client.pipeline() as pipe:
        pipe.hset(key, mapping=fields)
        pipe.expire(key, settings.agent_job_ttl_seconds)
        pipe.execute()

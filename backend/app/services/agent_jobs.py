"""Redis persistence and Celery submission for authenticated agent jobs."""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from typing import Any, cast
from uuid import uuid4

from app.config import settings
from redis import Redis
from redis.exceptions import RedisError

JOB_KEY_PREFIX = "athena:agent-job:"
JOB_EVENT_CHANNEL_PREFIX = "athena:agent-job-events:"
JOB_REQUEST_KEY_PREFIX = "athena:agent-job-request:"
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
_current_job_id: ContextVar[str | None] = ContextVar("agent_job_id", default=None)
logger = logging.getLogger(__name__)

_UPDATE_JOB_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end
local current_status = redis.call('HGET', KEYS[1], 'status')
if (current_status == 'cancelled'
    or current_status == 'succeeded'
    or current_status == 'failed')
    and ARGV[1] ~= current_status then
    return 0
end
for index = 3, #ARGV, 2 do
    redis.call('HSET', KEYS[1], ARGV[index], ARGV[index + 1])
end
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""

_START_JOB_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return -1
end
local current_status = redis.call('HGET', KEYS[1], 'status')
if current_status == 'succeeded'
    or current_status == 'failed'
    or current_status == 'cancelled' then
    return 0
end
redis.call(
    'HSET', KEYS[1],
    'status', 'running',
    'stage', 'running',
    'queue_latency_ms', ARGV[1],
    'updated_at', ARGV[2]
)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return 1
"""

_CREATE_IDEMPOTENT_JOB_SCRIPT = """
local existing = redis.call('GET', KEYS[1])
if existing then
    local separator = string.find(existing, '|', 1, true)
    local existing_job_id = string.sub(existing, 1, separator - 1)
    local existing_fingerprint = string.sub(existing, separator + 1)
    if existing_fingerprint ~= ARGV[2] then
        return {'conflict', existing_job_id}
    end
    if redis.call('EXISTS', KEYS[2] .. existing_job_id) == 1 then
        redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
        return {'replay', existing_job_id}
    end
    redis.call('DEL', KEYS[1])
end
redis.call('SET', KEYS[1], ARGV[1] .. '|' .. ARGV[2], 'EX', tonumber(ARGV[3]))
redis.call(
    'HSET', KEYS[2] .. ARGV[1],
    'user_id', ARGV[4],
    'trace_id', ARGV[5],
    'experiment_id', ARGV[6],
    'variant_id', ARGV[7],
    'status', 'queued',
    'stage', 'queued',
    'created_at', ARGV[8],
    'updated_at', ARGV[8],
    'request_key', KEYS[1]
)
redis.call('EXPIRE', KEYS[2] .. ARGV[1], tonumber(ARGV[3]))
return {'created', ARGV[1]}
"""

_CANCEL_JOB_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return -1
end
if redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[1] then
    return -1
end
local current_status = redis.call('HGET', KEYS[1], 'status')
if current_status == 'succeeded'
    or current_status == 'failed'
    or current_status == 'cancelled' then
    return 0
end
redis.call(
    'HSET', KEYS[1],
    'status', 'cancelled',
    'stage', 'cancelled',
    'cancel_requested', '1',
    'updated_at', ARGV[2]
)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return 1
"""


class QueueUnavailableError(Exception):
    """Redis or the Celery broker could not accept a job."""


class AgentJobCancelledError(Exception):
    """The authenticated caller requested cancellation of the current job."""


class IdempotencyConflictError(Exception):
    """An idempotency key was reused for a different chat request."""


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


def _request_key(user_id: str, idempotency_key: str) -> str:
    owner = sha256(user_id.encode()).hexdigest()
    request = sha256(idempotency_key.encode()).hexdigest()
    return f"{JOB_REQUEST_KEY_PREFIX}{owner}:{request}"


def _request_fingerprint(message: str, locale: str, conversation_id: str | None) -> str:
    payload = json.dumps(
        {"conversation_id": conversation_id, "locale": locale, "message": message},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode()).hexdigest()


def job_event_channel(job_id: str) -> str:
    return f"{JOB_EVENT_CHANNEL_PREFIX}{job_id}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
    experiment_id: str | None = None,
    variant_id: str | None = None,
    idempotency_key: str | None = None,
) -> str:
    """Create one owner-scoped job per stable client request and enqueue it."""
    # Imported lazily so service and API unit tests do not need to initialize Celery.
    from app.workers.tasks import run_agent_chat_task

    job_id = str(uuid4())
    key = _job_key(job_id)
    client = redis_client()
    enqueued_at = _now()
    request_key: str | None = None
    try:
        if idempotency_key:
            request_key = _request_key(user_id, idempotency_key)
            outcome = cast(
                list[str],
                client.eval(
                    _CREATE_IDEMPOTENT_JOB_SCRIPT,
                    2,
                    request_key,
                    JOB_KEY_PREFIX,
                    job_id,
                    _request_fingerprint(message, locale, conversation_id),
                    str(settings.agent_job_ttl_seconds),
                    user_id,
                    trace_id,
                    experiment_id or "",
                    variant_id or "",
                    enqueued_at,
                ),
            )
            state, resolved_job_id = outcome
            if state == "conflict":
                raise IdempotencyConflictError(
                    "Idempotency-Key уже использован для другого сообщения"
                )
            if state == "replay":
                return resolved_job_id
            job_id = resolved_job_id
            key = _job_key(job_id)
        else:
            with client.pipeline() as pipe:
                pipe.hset(
                    key,
                    mapping={
                        "user_id": user_id,
                        "trace_id": trace_id,
                        "experiment_id": experiment_id or "",
                        "variant_id": variant_id or "",
                        "status": "queued",
                        "stage": "queued",
                        "created_at": enqueued_at,
                        "updated_at": enqueued_at,
                    },
                )
                pipe.expire(key, settings.agent_job_ttl_seconds)
                pipe.execute()  # type: ignore[no-untyped-call]  # redis pipeline stub
        run_agent_chat_task.apply_async(
            kwargs={
                "job_id": job_id,
                "user_id": user_id,
                "message": message,
                "locale": locale,
                "conversation_id": conversation_id,
                "trace_id": trace_id,
                "experiment_id": experiment_id,
                "variant_id": variant_id,
            },
            task_id=job_id,
            queue=settings.agent_job_queue,
        )
    except IdempotencyConflictError:
        raise
    except Exception as exc:
        try:
            client.delete(key)
            if request_key is not None:
                client.delete(request_key)
        except RedisError:
            logger.warning("Could not remove rejected job %s", job_id, exc_info=True)
        raise QueueUnavailableError("Redis job queue is unavailable") from exc
    try:
        _publish_event(job_id, "queued")
    except RedisError:
        # The durable job record and broker submission are authoritative. SSE
        # subscribers receive the current state before listening for updates,
        # so a transient queued-event failure must not orphan accepted work.
        logger.warning("Could not publish queued event for job %s", job_id, exc_info=True)
    return job_id


def get_agent_job(job_id: str, user_id: str) -> dict[str, Any] | None:
    try:
        record = cast(dict[str, str], redis_client().hgetall(_job_key(job_id)))
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
        "experiment_id": record.get("experiment_id") or None,
        "variant_id": record.get("variant_id") or None,
        "status": status,
        "stage": record.get("stage") or fallback_stage,
    }
    if record.get("result"):
        response.update(json.loads(record["result"]))
    if record.get("error"):
        response["error"] = record["error"]
    return response


def mark_job_running(job_id: str) -> int | None:
    """Claim active work, or return ``None`` for a terminal/expired job."""
    client = redis_client()
    key = _job_key(job_id)
    created_at = cast(str | None, client.hget(key, "created_at"))
    queue_latency_ms = 0
    if created_at:
        queued = datetime.fromisoformat(created_at)
        queue_latency_ms = max(
            0,
            round((datetime.now(UTC) - queued).total_seconds() * 1_000),
        )
    started = int(
        cast(
            int | str,
            client.eval(
                _START_JOB_SCRIPT,
                1,
                key,
                str(queue_latency_ms),
                _now(),
                str(settings.agent_job_ttl_seconds),
            ),
        )
    )
    if started != 1:
        return None
    try:
        _publish_event(job_id, "running", {"queue_latency_ms": queue_latency_ms})
    except RedisError:
        logger.warning(
            "Could not publish running event for job %s after durable update",
            job_id,
            exc_info=True,
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
        transition = int(
            cast(
                int | str,
                client.eval(
                    _CANCEL_JOB_SCRIPT,
                    1,
                    key,
                    user_id,
                    _now(),
                    str(settings.agent_job_ttl_seconds),
                ),
            )
        )
        if transition == -1:
            return None
        if transition == 1:
            try:
                _publish_event(job_id, "cancelled")
            except RedisError:
                logger.warning(
                    "Could not publish cancelled event for job %s after durable update",
                    job_id,
                    exc_info=True,
                )
            from app.workers.celery_app import celery_app

            try:
                celery_app.control.revoke(job_id, terminate=False)
            except Exception:
                # Redis cancellation remains authoritative; revoke is only an
                # optimization for tasks that have not been consumed yet.
                logger.warning("Could not revoke cancelled job %s", job_id, exc_info=True)
        return get_agent_job(job_id, user_id)
    except RedisError as exc:
        raise QueueUnavailableError("Redis job store is unavailable") from exc


def job_is_cancelled(job_id: str) -> bool:
    try:
        record = cast(
            list[str | None],
            redis_client().hmget(_job_key(job_id), ["status", "cancel_requested"]),
        )
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
    job = cast(dict[str, str], redis_client().hgetall(_job_key(job_id)))
    payload: dict[str, Any] = {
        "job_id": job_id,
        "trace_id": job.get("trace_id") or job_id,
        "experiment_id": job.get("experiment_id") or None,
        "variant_id": job.get("variant_id") or None,
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
    arguments = [
        fields.get("status", ""),
        str(settings.agent_job_ttl_seconds),
    ]
    for name, value in fields.items():
        arguments.extend((name, value))
    updated = int(cast(int | str, client.eval(_UPDATE_JOB_SCRIPT, 1, key, *arguments)))
    if updated == 0:
        raise AgentJobCancelledError("Agent job was cancelled")
    if event is not None:
        try:
            _publish_event(job_id, event, event_details)
        except RedisError:
            # The hash update is authoritative. Subscribers reconnecting after
            # a transient Pub/Sub failure receive the current durable state.
            logger.warning(
                "Could not publish %s event for job %s after durable update",
                event,
                job_id,
                exc_info=True,
            )

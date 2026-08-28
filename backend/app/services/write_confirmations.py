"""Owner-scoped two-phase confirmation for state-changing agent tools."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from redis.exceptions import RedisError

from app.config import settings
from app.services import agent_conversations, agent_traces
from app.services.agent_jobs import QueueUnavailableError, redis_client
from app.tools.registry import build_tools, is_read_only_tool
from app.tools.write_context import confirmed_write_context


WRITE_ACTION_KEY_PREFIX = "athena:write-action:"
IDEMPOTENCY_KEY_PREFIX = "athena:write-idempotency:"
WRITE_LOCK_PREFIX = "athena:write-lock:"
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class WriteActionConflictError(ValueError):
    pass


class WriteActionInProgressError(RuntimeError):
    pass


def _action_key(action_id: str) -> str:
    return f"{WRITE_ACTION_KEY_PREFIX}{action_id}"


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _trace_tool_call(record: dict[str, str], tool_name: str, args: dict[str, Any]) -> str | None:
    """Create metadata-first tracing without making observability a write dependency."""
    if not record.get("trace_id"):
        return None
    try:
        return agent_traces.create_tool_call(
            run_id=record["trace_id"],
            tool_name=tool_name,
            tool_args=args,
            tool_step=0,
        )
    except Exception:
        return None


def _message(locale: str, tool_name: str) -> str:
    if locale == "ru":
        return f"Проверьте параметры и подтвердите операцию «{tool_name}». До подтверждения запись не выполняется."
    return f"Review and confirm the {tool_name} operation. Nothing is written before confirmation."


def stage_write_action(
    *,
    user_id: str,
    trace_id: str | None,
    conversation_id: str | None,
    locale: str,
    tool_name: str,
    tool_args: dict[str, Any],
) -> dict[str, Any]:
    action_id = str(uuid4())
    token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(seconds=settings.write_confirmation_ttl_seconds)
    record = {
        "user_id": user_id,
        "trace_id": trace_id or "",
        "conversation_id": conversation_id or "",
        "locale": locale,
        "tool_name": tool_name,
        "tool_args": json.dumps(tool_args, ensure_ascii=False, sort_keys=True),
        "token_digest": _token_digest(token),
        "status": "pending",
        "created_at": _now().isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    try:
        client = redis_client()
        with client.pipeline() as pipe:
            pipe.hset(_action_key(action_id), mapping=record)
            pipe.expire(_action_key(action_id), settings.write_confirmation_ttl_seconds)
            pipe.execute()
    except RedisError as exc:
        raise QueueUnavailableError("write confirmation store is unavailable") from exc
    return {
        "status": "confirmation_required",
        "message": _message(locale, tool_name),
        "write_action": {
            "action_id": action_id,
            "confirmation_token": token,
            "tool_name": tool_name,
            "preview": tool_args,
            "expires_at": expires_at.isoformat(),
        },
    }


def _owned_action(action_id: str, user_id: str, token: str) -> dict[str, str] | None:
    try:
        record = redis_client().hgetall(_action_key(action_id))
    except RedisError as exc:
        raise QueueUnavailableError("write confirmation store is unavailable") from exc
    if not record or record.get("user_id") != user_id:
        return None
    if not hmac.compare_digest(record.get("token_digest", ""), _token_digest(token)):
        return None
    return record


def _validate_idempotency_key(value: str) -> str:
    value = value.strip()
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
        raise ValueError(
            "Idempotency-Key must be 8-128 characters using letters, numbers, '.', '_', ':', or '-'"
        )
    return value


def confirm_write_action(
    *, action_id: str, user_id: str, confirmation_token: str, idempotency_key: str
) -> dict[str, Any] | None:
    key = _validate_idempotency_key(idempotency_key)
    record = _owned_action(action_id, user_id, confirmation_token)
    if record is None:
        return None
    if record.get("status") == "rejected":
        raise WriteActionConflictError("write action was rejected")

    client = redis_client()
    action_key = _action_key(action_id)
    try:
        client.hsetnx(action_key, "idempotency_key", key)
        claimed_key = client.hget(action_key, "idempotency_key")
        if claimed_key != key:
            raise WriteActionConflictError(
                "write action was already confirmed with another idempotency key"
            )

        ledger_key = f"{IDEMPOTENCY_KEY_PREFIX}{user_id}:{key}"
        client.set(ledger_key, action_id, nx=True, ex=settings.write_confirmation_ttl_seconds)
        if client.get(ledger_key) != action_id:
            raise WriteActionConflictError(
                "idempotency key was already used for another write action"
            )

        if record.get("status") == "confirmed" and record.get("result"):
            replay = json.loads(record["result"])
            replay["idempotent_replay"] = True
            return replay

        lock_key = f"{WRITE_LOCK_PREFIX}{action_id}"
        if not client.set(lock_key, key, nx=True, ex=30):
            raise WriteActionInProgressError("write action confirmation is already in progress")
    except RedisError as exc:
        raise QueueUnavailableError("write confirmation store is unavailable") from exc

    try:
        tools = {
            tool.name: tool
            for tool in build_tools(user_id, domains=("nutrition", "workout"))
        }
        tool = tools.get(record["tool_name"])
        requires_confirmation = bool(
            tool is not None and (tool.metadata or {}).get("requires_confirmation")
        )
        if tool is None or is_read_only_tool(tool) or not requires_confirmation:
            raise WriteActionConflictError("stored write tool is not available")
        args = json.loads(record["tool_args"])
        trace_call_id = _trace_tool_call(record, tool.name, args)
        started_at = perf_counter()
        try:
            with confirmed_write_context(key):
                result = tool.invoke(args)
        except Exception as exc:
            if trace_call_id is not None:
                try:
                    agent_traces.fail_tool_call(
                        tool_call_id=trace_call_id,
                        run_id=record["trace_id"],
                        error=exc,
                        latency_ms=agent_traces.elapsed_ms(started_at),
                    )
                except Exception:
                    pass
            raise
        if trace_call_id is not None:
            try:
                agent_traces.succeed_tool_call(
                    tool_call_id=trace_call_id,
                    run_id=record["trace_id"],
                    tool_result=result,
                    latency_ms=agent_traces.elapsed_ms(started_at),
                )
            except Exception:
                pass
        response = {
            "status": "confirmed",
            "action_id": action_id,
            "tool_name": tool.name,
            "tool_result": result,
            "idempotency_key": key,
            "idempotent_replay": bool(
                isinstance(result, dict) and result.get("idempotent_replay")
            ),
            "conversation_id": record.get("conversation_id") or None,
        }
        client.hset(
            action_key,
            mapping={
                "status": "confirmed",
                "confirmed_at": _now().isoformat(),
                "result": json.dumps(response, ensure_ascii=False),
            },
        )
        if record.get("conversation_id"):
            try:
                agent_conversations.append_assistant_message(
                    record["conversation_id"],
                    "Операция подтверждена и выполнена."
                    if record.get("locale") == "ru"
                    else "The operation was confirmed and completed.",
                )
            except Exception:
                pass
        return response
    finally:
        try:
            client.delete(f"{WRITE_LOCK_PREFIX}{action_id}")
        except RedisError:
            pass


def reject_write_action(
    *, action_id: str, user_id: str, confirmation_token: str
) -> dict[str, Any] | None:
    record = _owned_action(action_id, user_id, confirmation_token)
    if record is None:
        return None
    if record.get("status") == "confirmed":
        raise WriteActionConflictError("confirmed write action cannot be rejected")
    try:
        redis_client().hset(
            _action_key(action_id),
            mapping={"status": "rejected", "rejected_at": _now().isoformat()},
        )
    except RedisError as exc:
        raise QueueUnavailableError("write confirmation store is unavailable") from exc
    return {"status": "rejected", "action_id": action_id}

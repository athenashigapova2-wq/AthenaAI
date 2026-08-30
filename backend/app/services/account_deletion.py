"""Permanent, owner-scoped account deletion across runtime and durable stores."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.services.agent_jobs import JOB_KEY_PREFIX, redis_client
from app.services.supabase import get_supabase
from app.services.write_confirmations import (
    IDEMPOTENCY_KEY_PREFIX,
    WRITE_ACTION_KEY_PREFIX,
    WRITE_LOCK_PREFIX,
)
from redis.exceptions import RedisError


class AccountDeletionError(RuntimeError):
    """The account could not be fully deleted."""


class AccountDeletionDependencyError(AccountDeletionError):
    """A dependency failed before the Auth identity was removed."""


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountDeletionResult:
    storage_objects_deleted: int
    runtime_records_scrubbed: int


def delete_account(user_id: str) -> AccountDeletionResult:
    """Delete files and runtime state, then remove Auth and cascading DB rows.

    Auth is deliberately deleted last. If storage or Redis cleanup fails, the
    caller keeps a valid account and can retry without leaving an unreachable
    orphaned identity.
    """
    normalized_user_id = str(UUID(user_id))
    client = get_supabase()

    runtime_records = _scrub_runtime_state(normalized_user_id)
    storage_objects = _delete_user_storage(client, normalized_user_id)
    try:
        client.auth.admin.delete_user(normalized_user_id, should_soft_delete=False)
    except Exception as exc:
        raise AccountDeletionError("Supabase Auth account deletion failed") from exc

    return AccountDeletionResult(
        storage_objects_deleted=storage_objects,
        runtime_records_scrubbed=runtime_records,
    )


def _scrub_runtime_state(user_id: str) -> int:
    """Cancel jobs and erase user-owned Redis payloads before Auth deletion."""
    try:
        client = redis_client()
        affected = 0
        for key in client.scan_iter(match=f"{JOB_KEY_PREFIX}*", count=200):
            record = client.hgetall(key)
            if record.get("user_id") != user_id:
                continue
            job_id = str(key).removeprefix(JOB_KEY_PREFIX)
            _revoke_job_best_effort(job_id)
            with client.pipeline() as pipe:
                pipe.hset(
                    key,
                    mapping={
                        "status": "cancelled",
                        "stage": "cancelled",
                        "cancel_requested": "1",
                    },
                )
                pipe.hdel(
                    key,
                    "user_id",
                    "trace_id",
                    "result",
                    "error",
                    "experiment_id",
                    "variant_id",
                )
                # Keep a short content-free tombstone so an in-flight worker
                # can still observe cooperative cancellation.
                pipe.expire(key, 600)
                pipe.execute()
            affected += 1

        action_keys: list[str] = []
        for key in client.scan_iter(match=f"{WRITE_ACTION_KEY_PREFIX}*", count=200):
            if client.hget(key, "user_id") != user_id:
                continue
            action_id = str(key).removeprefix(WRITE_ACTION_KEY_PREFIX)
            action_keys.extend((str(key), f"{WRITE_LOCK_PREFIX}{action_id}"))
        ledger_keys = [
            str(key)
            for key in client.scan_iter(
                match=f"{IDEMPOTENCY_KEY_PREFIX}{user_id}:*",
                count=200,
            )
        ]
        keys_to_delete = action_keys + ledger_keys
        if keys_to_delete:
            client.delete(*keys_to_delete)
            affected += len(keys_to_delete)
        return affected
    except RedisError as exc:
        raise AccountDeletionDependencyError(
            "Runtime account data could not be removed"
        ) from exc


def _revoke_job_best_effort(job_id: str) -> None:
    try:
        from app.workers.celery_app import celery_app

        celery_app.control.revoke(job_id, terminate=False)
    except Exception:
        # The Redis cancellation tombstone remains authoritative.
        logger.warning("Could not revoke account-deletion job %s", job_id, exc_info=True)


def _delete_user_storage(client: Any, user_id: str) -> int:
    """Remove every object under the mandatory per-user storage prefix."""
    try:
        buckets = list(client.storage.list_buckets() or [])
        deleted = 0
        for bucket in buckets:
            bucket_id = _value(bucket, "id") or _value(bucket, "name")
            if not bucket_id:
                continue
            bucket_api = client.storage.from_(str(bucket_id))
            paths = _list_storage_paths(bucket_api, user_id)
            for start in range(0, len(paths), 100):
                batch = paths[start : start + 100]
                if batch:
                    bucket_api.remove(batch)
                    deleted += len(batch)
        return deleted
    except Exception as exc:
        raise AccountDeletionDependencyError(
            "User files could not be removed"
        ) from exc


def _list_storage_paths(bucket_api: Any, user_prefix: str) -> list[str]:
    files: list[str] = []
    pending = [user_prefix]
    while pending:
        prefix = pending.pop()
        offset = 0
        while True:
            entries = list(
                bucket_api.list(prefix, {"limit": 100, "offset": offset}) or []
            )
            for entry in entries:
                name = str(_value(entry, "name") or "")
                if not name or name in {".", ".."}:
                    continue
                object_path = f"{prefix}/{name}"
                if _value(entry, "id"):
                    files.append(object_path)
                else:
                    pending.append(object_path)
            if len(entries) < 100:
                break
            offset += 100
    return files


def _value(record: Any, name: str) -> Any:
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)

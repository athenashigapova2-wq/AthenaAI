"""Database-backed idempotency for confirmed write tools."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class IdempotencyConflictError(ValueError):
    """One idempotency key was reused with a different write payload."""


def payload_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _existing_row(client: Any, table_name: str, user_id: str, key: str) -> dict[str, Any] | None:
    response = (
        client.table(table_name)
        .select("*")
        .eq("user_id", user_id)
        .eq("idempotency_key", key)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def insert_idempotently(
    client: Any,
    table_name: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> tuple[dict[str, Any], bool]:
    """Insert once, returning the original row on a safe replay.

    The partial unique database index closes the concurrency race. If another
    request wins the insert, the failed contender reads and validates that row.
    """
    user_id = str(payload["user_id"])
    fingerprint = payload_fingerprint(payload)
    existing = _existing_row(client, table_name, user_id, idempotency_key)
    if existing is not None:
        if existing.get("idempotency_fingerprint") != fingerprint:
            raise IdempotencyConflictError(
                "idempotency key was already used with a different payload"
            )
        return existing, True

    stored_payload = {
        **payload,
        "idempotency_key": idempotency_key,
        "idempotency_fingerprint": fingerprint,
    }
    try:
        response = client.table(table_name).insert(stored_payload).execute()
    except Exception:
        existing = _existing_row(client, table_name, user_id, idempotency_key)
        if existing is None:
            raise
        if existing.get("idempotency_fingerprint") != fingerprint:
            raise IdempotencyConflictError(
                "idempotency key was already used with a different payload"
            )
        return existing, True

    rows = response.data or []
    if not rows:
        raise RuntimeError(f"{table_name} insert returned no row")
    return rows[0], False

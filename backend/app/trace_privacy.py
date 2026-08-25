"""Deterministic privacy policy for observability payloads."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.config import settings

TracePayloadMode = Literal["full", "redacted", "none"]

REDACTION_VERSION = "v1"
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+\S+")
_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|token)\b\s*[:=]\s*[^\s,;}]+"
)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){10,15}(?!\w)")


def pseudonymous_actor_id(user_id: str) -> str:
    """Return a stable non-reversible analytics identifier for one actor."""
    return hashlib.sha256(f"athena-trace-actor:v1:{user_id}".encode()).hexdigest()[:32]


def tool_arg_summary(tool_args: dict[str, Any], *, schema_version: int) -> dict[str, int]:
    """Describe a tool input without retaining argument names or values."""
    return {
        "arg_schema_version": schema_version,
        "arg_count": len(tool_args),
    }


def tool_result_summary(tool_result: Any) -> dict[str, int | str | None]:
    """Describe result cardinality without retaining domain payload values."""
    row_count = _result_row_count(tool_result)
    empty = tool_result is None or tool_result == {} or tool_result == []
    return {
        "result_status": "empty" if empty else "success",
        "result_row_count": row_count,
    }


def effective_trace_content_mode() -> str:
    """Return the explicit content switch; safe metadata is stored separately."""
    return settings.trace_content_mode


def payload_mode_for_run(run_id: str) -> TracePayloadMode:
    """Choose one stable payload mode for all events in a run."""
    del run_id
    if settings.trace_raw_payload_retention_days == 0:
        return "none"
    content_mode = effective_trace_content_mode()
    if content_mode == "full":
        return "full"
    if content_mode == "redacted":
        return "redacted"
    return "none"


def payload_expiry(mode: TracePayloadMode) -> str | None:
    if mode == "none":
        return None
    expires = datetime.now(timezone.utc) + timedelta(
        days=settings.trace_raw_payload_retention_days
    )
    return expires.isoformat()


def protect_payload(value: Any, mode: TracePayloadMode) -> Any:
    """Apply truncation and, where required, recursive redaction."""
    if mode == "none":
        return None
    return _protect(value, redact=mode == "redacted")


def protect_mapping(value: Any, mode: TracePayloadMode) -> dict[str, Any]:
    protected = protect_payload(value, mode)
    return protected if isinstance(protected, dict) else {}


def safe_error(error: BaseException, mode: TracePayloadMode) -> str:
    """Errors are always redacted because exception text often contains secrets."""
    if mode == "none":
        return type(error).__name__
    return str(_protect(f"{type(error).__name__}: {error}", redact=True))


def _result_row_count(value: Any) -> int | None:
    if isinstance(value, (list, tuple)):
        return len(value)
    if not isinstance(value, dict):
        return None
    for key in ("row_count", "count", "total_count"):
        count = value.get(key)
        if isinstance(count, int) and count >= 0:
            return count
    for key in ("rows", "records", "entries", "items", "meals", "weights", "data"):
        rows = value.get(key)
        if isinstance(rows, list):
            return len(rows)
    return None


def _protect(value: Any, *, redact: bool) -> Any:
    if isinstance(value, str):
        text = value[: settings.trace_payload_max_chars]
        return _redact_text(text) if redact else text
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= settings.trace_payload_max_collection_items:
                result["_truncated"] = True
                break
            normalized_key = str(key)[:200]
            if redact and re.search(
                r"(?i)(authorization|password|secret|token|api[_-]?key)",
                normalized_key,
            ):
                result[normalized_key] = "[REDACTED]"
            else:
                result[normalized_key] = _protect(item, redact=redact)
        return result
    if isinstance(value, (list, tuple)):
        return [
            _protect(item, redact=redact)
            for item in value[: settings.trace_payload_max_collection_items]
        ]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _protect(str(value), redact=redact)


def _redact_text(text: str) -> str:
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _JWT_RE.sub("[JWT_REDACTED]", text)
    text = _EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = _PHONE_RE.sub("[PHONE_REDACTED]", text)
    return _SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)

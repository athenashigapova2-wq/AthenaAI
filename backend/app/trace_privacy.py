"""Deterministic classification and privacy policy for observability payloads."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Literal

from app.config import settings

TracePayloadMode = Literal["full", "redacted", "none"]


class DataClassification(StrEnum):
    """Sensitivity labels used by the trace storage boundary."""

    PUBLIC = "public"
    INTERNAL = "internal"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class TracePayloadKind(StrEnum):
    """Domain context needed to classify otherwise ambiguous payload fields."""

    GENERIC = "generic"
    PROFILE = "profile"
    CONVERSATION = "conversation"
    TOOL_ARGS = "tool_args"
    TOOL_RESULT = "tool_result"
    ERROR = "error"


REDACTION_VERSION = "v2-classified"
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+\S+")
_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|token)\b\s*[:=]\s*[^\s,;}]+"
)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){10,15}(?!\w)")
_RESTRICTED_FIELDS = re.compile(
    r"(?i)(authorization|password|passwd|secret|token|api[_-]?key|credential|cookie|session)"
)
_SENSITIVE_FIELDS = re.compile(
    r"(?i)(medical|diagnos|disease|condition|symptom|medication|allerg|pregnan|cycle|"
    r"weight|height|bmi|body[_ -]?fat|calori|protein|carb|macro|fat[_ -]?g|sleep|"
    r"health|blood|glucose|pressure|injury|disability|meal|food|diet)"
)
_PERSONAL_FIELDS = re.compile(
    r"(?i)(email|phone|mobile|address|first[_ -]?name|last[_ -]?name|full[_ -]?name|"
    r"display[_ -]?name|birth|age|gender|sex|user[_ -]?id|conversation[_ -]?id)"
)


def classify_field(
    field_name: str,
    *,
    payload_kind: TracePayloadKind = TracePayloadKind.GENERIC,
) -> DataClassification:
    """Classify one profile/conversation/tool field before persistence."""
    normalized = field_name.strip().lower()
    if _RESTRICTED_FIELDS.search(normalized):
        return DataClassification.RESTRICTED
    if _SENSITIVE_FIELDS.search(normalized):
        return DataClassification.SENSITIVE
    if _PERSONAL_FIELDS.search(normalized):
        return DataClassification.PERSONAL
    if payload_kind in {TracePayloadKind.PROFILE, TracePayloadKind.CONVERSATION}:
        return DataClassification.SENSITIVE
    return DataClassification.INTERNAL


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
    expires = datetime.now(timezone.utc) + timedelta(days=settings.trace_raw_payload_retention_days)
    return expires.isoformat()


def protect_payload(
    value: Any,
    mode: TracePayloadMode,
    *,
    payload_kind: TracePayloadKind = TracePayloadKind.GENERIC,
) -> Any:
    """Sanitize a payload at the final boundary before trace persistence.

    Restricted credentials are removed in every mode, including local ``full``.
    Redacted conversation/profile content is not retained because regex-only PII
    removal cannot provide a reliable privacy guarantee for free-form text.
    """
    if mode == "none":
        return None
    if mode == "redacted" and payload_kind == TracePayloadKind.CONVERSATION:
        return "[SENSITIVE_CONTENT_REDACTED]"
    return _protect(value, mode=mode, payload_kind=payload_kind)


def protect_mapping(
    value: Any,
    mode: TracePayloadMode,
    *,
    payload_kind: TracePayloadKind = TracePayloadKind.GENERIC,
) -> dict[str, Any]:
    protected = protect_payload(value, mode, payload_kind=payload_kind)
    return protected if isinstance(protected, dict) else {}


def safe_error(error: BaseException, mode: TracePayloadMode) -> str:
    """Persist only error type outside explicitly local full-content tracing."""
    if mode != "full":
        return type(error).__name__
    return str(
        _protect(
            f"{type(error).__name__}: {error}",
            mode="redacted",
            payload_kind=TracePayloadKind.ERROR,
        )
    )


def sanitize_provider_text(text: str) -> str:
    """Remove credentials before free-form content leaves the backend."""
    return _redact_restricted_text(text)


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


def _protect(
    value: Any,
    *,
    mode: TracePayloadMode,
    payload_kind: TracePayloadKind,
) -> Any:
    if isinstance(value, str):
        text = value[: settings.trace_payload_max_chars]
        return _redact_text(text) if mode == "redacted" else _redact_restricted_text(text)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= settings.trace_payload_max_collection_items:
                result["_truncated"] = True
                break
            normalized_key = str(key)[:200]
            classification = classify_field(normalized_key, payload_kind=payload_kind)
            if classification == DataClassification.RESTRICTED:
                result[normalized_key] = "[RESTRICTED_REDACTED]"
            elif mode == "redacted" and classification in {
                DataClassification.PERSONAL,
                DataClassification.SENSITIVE,
            }:
                result[normalized_key] = _classification_placeholder(
                    item,
                    classification,
                )
            else:
                result[normalized_key] = _protect(
                    item,
                    mode=mode,
                    payload_kind=payload_kind,
                )
        return result
    if isinstance(value, (list, tuple)):
        return [
            _protect(item, mode=mode, payload_kind=payload_kind)
            for item in value[: settings.trace_payload_max_collection_items]
        ]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _protect(str(value), mode=mode, payload_kind=payload_kind)


def _classification_placeholder(value: Any, classification: DataClassification) -> str:
    if classification == DataClassification.PERSONAL and isinstance(value, str):
        redacted = _redact_text(value)
        if redacted != value:
            return redacted
    return f"[{classification.value.upper()}_REDACTED]"


def _redact_text(text: str) -> str:
    text = _redact_restricted_text(text)
    text = _EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    return _PHONE_RE.sub("[PHONE_REDACTED]", text)


def _redact_restricted_text(text: str) -> str:
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _JWT_RE.sub("[JWT_REDACTED]", text)
    return _SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)

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


def effective_trace_payload_policy() -> str:
    """Resolve the explicit policy or the safe environment default."""
    configured = settings.trace_payload_policy
    if configured != "auto":
        return configured
    environment = settings.app_env.strip().lower()
    if environment in {"dev", "development", "local", "test"}:
        return "full"
    if environment in {"stage", "staging"}:
        return "sampled_redacted"
    return "structured_only"


def payload_mode_for_run(run_id: str) -> TracePayloadMode:
    """Choose one stable payload mode for all events in a run."""
    if settings.trace_raw_payload_retention_days == 0:
        return "none"
    policy = effective_trace_payload_policy()
    if policy == "full":
        return "full"
    if policy == "structured_only":
        return "none"
    return "redacted" if _sampled(run_id, settings.trace_payload_sample_rate) else "none"


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


def _sampled(run_id: str, rate: float) -> bool:
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    digest = hashlib.sha256(run_id.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(2**64)
    return bucket < rate


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

"""Deterministic checks for trace payload policy and redaction."""

import pytest

from app.config import Settings, settings
from app.trace_privacy import (
    effective_trace_content_mode,
    payload_mode_for_run,
    protect_mapping,
    protect_payload,
    safe_error,
    tool_arg_summary,
    tool_result_summary,
)


def test_content_is_off_by_default() -> None:
    assert settings.trace_content_mode == "off"
    assert effective_trace_content_mode() == "off"


def test_redacted_mode_removes_sensitive_values(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trace_content_mode", "redacted")
    monkeypatch.setattr(settings, "trace_raw_payload_retention_days", 7)
    mode = payload_mode_for_run("11111111-1111-4111-8111-111111111111")
    assert mode == "redacted"
    protected = protect_mapping(
        {
            "email": "anna@example.com",
            "authorization": "Bearer eyJabc.def.signature",
            "nested": {"phone": "+7 999 123-45-67"},
        },
        mode,
    )
    assert protected["email"] == "[EMAIL_REDACTED]"
    assert protected["authorization"] == "[REDACTED]"
    assert protected["nested"]["phone"] == "[PHONE_REDACTED]"


def test_production_keeps_metrics_without_payload(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trace_content_mode", "off")
    monkeypatch.setattr(settings, "trace_raw_payload_retention_days", 7)
    mode = payload_mode_for_run("22222222-2222-4222-8222-222222222222")
    assert mode == "none"
    assert protect_payload("private prompt", mode) is None
    assert protect_mapping({"meal": "private"}, mode) == {}
    assert safe_error(RuntimeError("token=secret"), mode) == "RuntimeError"


def test_development_full_payload_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trace_content_mode", "full")
    monkeypatch.setattr(settings, "trace_raw_payload_retention_days", 7)
    monkeypatch.setattr(settings, "trace_payload_max_chars", 100)
    mode = payload_mode_for_run("33333333-3333-4333-8333-333333333333")
    assert mode == "full"
    assert protect_payload("x" * 200, mode) == "x" * 100


def test_tool_metadata_contains_no_argument_values() -> None:
    args = tool_arg_summary(
        {"weight": 72.5, "medical_condition": "private"},
        schema_version=2,
    )
    assert args == {"arg_schema_version": 2, "arg_count": 2}
    assert "72.5" not in str(args)
    assert "private" not in str(args)

    result = tool_result_summary({"records": [{"weight": 72}, {"weight": 71.5}]})
    assert result == {"result_status": "success", "result_row_count": 2}


def test_empty_tool_result_has_structured_status() -> None:
    assert tool_result_summary([]) == {
        "result_status": "empty",
        "result_row_count": 0,
    }


def test_full_content_is_rejected_in_production() -> None:
    with pytest.raises(ValueError, match="allowed only in local/dev/test"):
        Settings(
            app_env="production",
            trace_content_mode="full",
            _env_file=None,
        )

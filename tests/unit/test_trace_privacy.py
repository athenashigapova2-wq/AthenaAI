"""Deterministic checks for trace payload policy and redaction."""

import pytest

from app.config import Settings, settings
from app.trace_privacy import (
    DataClassification,
    TracePayloadKind,
    classify_field,
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
    assert protected["authorization"] == "[RESTRICTED_REDACTED]"
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


def test_data_classification_covers_profile_conversation_and_tools() -> None:
    assert (
        classify_field("medical_condition", payload_kind=TracePayloadKind.PROFILE)
        == DataClassification.SENSITIVE
    )
    assert (
        classify_field("email", payload_kind=TracePayloadKind.PROFILE)
        == DataClassification.PERSONAL
    )
    assert (
        classify_field("access_token", payload_kind=TracePayloadKind.TOOL_ARGS)
        == DataClassification.RESTRICTED
    )
    assert (
        classify_field("row_count", payload_kind=TracePayloadKind.TOOL_RESULT)
        == DataClassification.INTERNAL
    )


def test_sensitive_fields_never_enter_redacted_trace() -> None:
    private_values = {
        "weight": 72.5,
        "calories": 1_800,
        "medical_condition": "diabetes",
        "email": "anna@example.com",
        "access_token": "eyJabc.def.signature",
        "nested": {"allergies": ["peanuts"]},
    }
    protected = protect_mapping(
        private_values,
        "redacted",
        payload_kind=TracePayloadKind.TOOL_ARGS,
    )
    serialized = str(protected)
    for sensitive_value in (
        "72.5",
        "1800",
        "diabetes",
        "anna@example.com",
        "eyJabc.def.signature",
        "peanuts",
    ):
        assert sensitive_value not in serialized


def test_redacted_conversation_never_persists_free_form_text() -> None:
    prompt = "Меня зовут Анна, мой вес 72.5 кг и у меня диабет"
    assert (
        protect_payload(
            prompt,
            "redacted",
            payload_kind=TracePayloadKind.CONVERSATION,
        )
        == "[SENSITIVE_CONTENT_REDACTED]"
    )


def test_restricted_fields_never_enter_even_full_local_trace() -> None:
    protected = protect_mapping(
        {
            "authorization": "Bearer private",
            "query": "safe local value token=private-secret",
        },
        "full",
        payload_kind=TracePayloadKind.TOOL_ARGS,
    )
    assert protected == {
        "authorization": "[RESTRICTED_REDACTED]",
        "query": "safe local value token=[REDACTED]",
    }


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

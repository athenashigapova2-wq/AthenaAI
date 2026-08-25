"""Deterministic checks for trace payload policy and redaction."""

import pytest

from app.config import settings
from app.trace_privacy import (
    effective_trace_payload_policy,
    payload_mode_for_run,
    protect_mapping,
    protect_payload,
    safe_error,
)


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ("development", "full"),
        ("staging", "sampled_redacted"),
        ("production", "structured_only"),
    ],
)
def test_auto_policy_maps_environment(monkeypatch, environment: str, expected: str) -> None:
    monkeypatch.setattr(settings, "trace_payload_policy", "auto")
    monkeypatch.setattr(settings, "app_env", environment)
    assert effective_trace_payload_policy() == expected


def test_staging_redacts_sampled_payload(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trace_payload_policy", "sampled_redacted")
    monkeypatch.setattr(settings, "trace_payload_sample_rate", 1.0)
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
    monkeypatch.setattr(settings, "trace_payload_policy", "structured_only")
    monkeypatch.setattr(settings, "trace_raw_payload_retention_days", 7)
    mode = payload_mode_for_run("22222222-2222-4222-8222-222222222222")
    assert mode == "none"
    assert protect_payload("private prompt", mode) is None
    assert protect_mapping({"meal": "private"}, mode) == {}
    assert safe_error(RuntimeError("token=secret"), mode) == "RuntimeError"


def test_development_full_payload_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trace_payload_policy", "full")
    monkeypatch.setattr(settings, "trace_raw_payload_retention_days", 7)
    monkeypatch.setattr(settings, "trace_payload_max_chars", 100)
    mode = payload_mode_for_run("33333333-3333-4333-8333-333333333333")
    assert mode == "full"
    assert protect_payload("x" * 200, mode) == "x" * 100

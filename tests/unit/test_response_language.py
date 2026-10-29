"""Regression coverage for response language and provider-output sanitation."""

import pytest
from app.agents.common.response_pipeline import _sanitize_internal_notation
from app.agents.prompts import localized_system_prompt, response_locale

pytestmark = pytest.mark.unit


def test_cyrillic_message_overrides_english_interface_locale() -> None:
    assert response_locale("en", "Что приготовить из творога?") == "ru"


def test_han_message_overrides_english_interface_locale() -> None:
    assert response_locale("en", "豆腐可以做什么？") == "zh"


def test_latin_message_keeps_explicit_interface_locale() -> None:
    assert response_locale("es", "Que puedo preparar hoy?") == "es"


def test_internal_provider_tool_marker_never_reaches_answer() -> None:
    answer = _sanitize_internal_notation(
        "[GET_GETMYPROFILE] Приготовьте сырники из творога.",
        "ru",
    )
    assert answer == "Приготовьте сырники из творога."
    assert "GETMYPROFILE" not in answer


def test_prompt_prioritizes_latest_user_message() -> None:
    prompt = localized_system_prompt("System policy.", "ru")
    assert "Answer the latest user message directly" in prompt
    assert "Reply only in Russian" in prompt

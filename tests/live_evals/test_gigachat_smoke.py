"""Minimal real-provider smoke test guarded by the live-eval opt-in gates."""

import pytest
from app.config import settings
from app.llm import _get_gigachat

pytestmark = pytest.mark.live


def test_gigachat_tls_verified_smoke() -> None:
    model = _get_gigachat(settings.gigachat_model, temperature=0.0)
    response = model.invoke("Ответь только одним словом: готов")

    assert str(response.content).strip()

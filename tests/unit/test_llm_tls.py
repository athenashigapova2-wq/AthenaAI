"""TLS verification must never be disabled by the canonical provider client."""

from unittest.mock import patch

from app.config import settings
from app.llm import _get_gigachat


def test_gigachat_uses_tls_verification_and_configured_ca_bundle() -> None:
    _get_gigachat.cache_clear()
    with (
        patch.object(settings, "gigachat_auth_key", "test-credential"),
        patch.object(settings, "gigachat_ca_bundle_file", "/run/secrets/gigachat-ca.pem"),
        patch("langchain_gigachat.GigaChat") as constructor,
    ):
        _get_gigachat("GigaChat-2", temperature=0.0)

    kwargs = constructor.call_args.kwargs
    assert kwargs["verify_ssl_certs"] is True
    assert kwargs["ca_bundle_file"] == "/run/secrets/gigachat-ca.pem"
    assert kwargs["temperature"] == 0.0
    _get_gigachat.cache_clear()


def test_gigachat_never_injects_an_empty_ca_bundle_path() -> None:
    _get_gigachat.cache_clear()
    with (
        patch.object(settings, "gigachat_auth_key", "test-credential"),
        patch.object(settings, "gigachat_ca_bundle_file", "  "),
        patch("langchain_gigachat.GigaChat") as constructor,
    ):
        _get_gigachat("GigaChat-2")

    kwargs = constructor.call_args.kwargs
    assert kwargs["verify_ssl_certs"] is True
    assert "ca_bundle_file" not in kwargs
    _get_gigachat.cache_clear()


def test_source_does_not_disable_tls_verification() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "backend/app/llm.py").read_text(
        encoding="utf-8"
    )
    assert '"verify_ssl_certs": False' not in source

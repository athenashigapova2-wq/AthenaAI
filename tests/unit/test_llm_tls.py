"""TLS verification must never be disabled by the canonical provider client."""

from hashlib import sha256
from ssl import PEM_cert_to_DER_cert
from unittest.mock import patch

import pytest
from app.config import BACKEND_DIR, settings
from app.llm import _get_gigachat, gigachat_ca_bundle_path

EXPECTED_GIGACHAT_CA_FINGERPRINT = (
    "d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31"
)


def test_committed_gigachat_trust_anchor_has_pinned_fingerprint() -> None:
    pem = gigachat_ca_bundle_path().read_text(encoding="ascii")
    der = PEM_cert_to_DER_cert(pem)

    assert sha256(der).hexdigest() == EXPECTED_GIGACHAT_CA_FINGERPRINT


def test_gigachat_uses_tls_verification_and_configured_ca_bundle(tmp_path) -> None:
    bundle = tmp_path / "gigachat-ca.pem"
    bundle.write_bytes((BACKEND_DIR / "certs/russian_trusted_root_ca_pem.crt").read_bytes())
    _get_gigachat.cache_clear()
    with (
        patch.object(settings, "gigachat_auth_key", "test-credential"),
        patch.object(settings, "gigachat_ca_bundle_file", str(bundle)),
        patch("langchain_gigachat.GigaChat") as constructor,
    ):
        _get_gigachat("GigaChat-2", temperature=0.0)

    kwargs = constructor.call_args.kwargs
    assert kwargs["verify_ssl_certs"] is True
    assert kwargs["ca_bundle_file"] == str(bundle)
    assert kwargs["temperature"] == 0.0
    _get_gigachat.cache_clear()


def test_empty_ca_setting_uses_the_committed_trust_anchor() -> None:
    _get_gigachat.cache_clear()
    with (
        patch.object(settings, "gigachat_auth_key", "test-credential"),
        patch.object(settings, "gigachat_ca_bundle_file", "  "),
        patch("langchain_gigachat.GigaChat") as constructor,
    ):
        _get_gigachat("GigaChat-2")

    kwargs = constructor.call_args.kwargs
    assert kwargs["verify_ssl_certs"] is True
    assert kwargs["ca_bundle_file"] == str(gigachat_ca_bundle_path())
    _get_gigachat.cache_clear()


def test_missing_ca_bundle_fails_before_provider_initialization(tmp_path) -> None:
    _get_gigachat.cache_clear()
    with (
        patch.object(settings, "gigachat_auth_key", "test-credential"),
        patch.object(settings, "gigachat_ca_bundle_file", str(tmp_path / "missing.pem")),
        patch("langchain_gigachat.GigaChat") as constructor,
        pytest.raises(RuntimeError, match="does not exist"),
    ):
        _get_gigachat("GigaChat-2")

    constructor.assert_not_called()
    _get_gigachat.cache_clear()


def test_source_does_not_disable_tls_verification() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "backend/app/llm.py").read_text(
        encoding="utf-8"
    )
    assert '"verify_ssl_certs": False' not in source

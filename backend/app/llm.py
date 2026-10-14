"""Provider factory for Athena LLMs.

This module knows how to construct provider clients. Routing, privacy,
resilience, tracing and invocation belong to ``app.ai_execution``.
"""

from functools import lru_cache
from pathlib import Path
from ssl import PEM_cert_to_DER_cert

from langchain_core.language_models import BaseChatModel

from app.config import BACKEND_DIR, DEFAULT_GIGACHAT_CA_BUNDLE, settings
from app.mock_llm import AthenaMockChatModel
from app.model_routing import ModelSelection


def gigachat_ca_bundle_path() -> Path:
    """Resolve and validate the dedicated GigaChat trust anchor."""
    configured = settings.gigachat_ca_bundle_file.strip() or DEFAULT_GIGACHAT_CA_BUNDLE
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = BACKEND_DIR / path
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(f"GIGACHAT_CA_BUNDLE_FILE does not exist: {path}")
    try:
        contents = path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"GIGACHAT_CA_BUNDLE_FILE is not a readable PEM file: {path}") from exc
    if "-----BEGIN CERTIFICATE-----" not in contents or "-----END CERTIFICATE-----" not in contents:
        raise RuntimeError(f"GIGACHAT_CA_BUNDLE_FILE is not a PEM certificate bundle: {path}")
    first_certificate_end = contents.find("-----END CERTIFICATE-----")
    first_certificate = contents[
        : first_certificate_end + len("-----END CERTIFICATE-----")
    ]
    try:
        PEM_cert_to_DER_cert(first_certificate)
    except ValueError as exc:
        raise RuntimeError(f"GIGACHAT_CA_BUNDLE_FILE contains an invalid PEM certificate: {path}") from exc
    return path


@lru_cache(maxsize=8)
def _get_gigachat(model: str, *, temperature: float | None = None) -> BaseChatModel:
    from langchain_gigachat import GigaChat

    if not settings.gigachat_auth_key:
        raise RuntimeError("GIGACHAT_AUTH_KEY must be set")
    kwargs = {
        "credentials": settings.gigachat_auth_key,
        "scope": settings.gigachat_scope,
        "model": model,
        "verify_ssl_certs": True,
        "profanity_check": False,
        "timeout": 60,
        "ca_bundle_file": str(gigachat_ca_bundle_path()),
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    return GigaChat(**kwargs)


@lru_cache(maxsize=16)
def _get_mock_llm(
    model: str,
    *,
    node_name: str,
    purpose: str,
) -> BaseChatModel:
    return AthenaMockChatModel(
        model_name=model,
        node_name=node_name,
        purpose=purpose,
        latency_ms=settings.mock_llm_latency_ms,
    )


def create_provider_model(
    *,
    selection: ModelSelection,
    node_name: str,
    purpose: str,
    temperature: float | None = None,
) -> BaseChatModel:
    """Construct the selected provider model without invoking it."""
    if selection.provider == "mock":
        return _get_mock_llm(
            selection.model_name,
            node_name=node_name,
            purpose=purpose,
        )
    return _get_gigachat(selection.model_name, temperature=temperature)

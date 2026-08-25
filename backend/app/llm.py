"""Provider factory for Athena LLMs.

This module knows how to construct provider clients. Routing, privacy,
resilience, tracing and invocation belong to ``app.ai_execution``.
"""

from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from app.config import settings
from app.model_routing import ModelSelection
from app.mock_llm import AthenaMockChatModel


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
    }
    if settings.gigachat_ca_bundle_file.strip():
        kwargs["ca_bundle_file"] = settings.gigachat_ca_bundle_file.strip()
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

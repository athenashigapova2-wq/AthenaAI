"""Обёртка над LLM-провайдером.

Единственное место в проекте, которое знает, что модель — GigaChat.
Агенты работают с абстракцией BaseChatModel, поэтому смена провайдера
затрагивает только этот файл.
"""

from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from app.config import settings


@lru_cache(maxsize=1)
def _get_gigachat(model: str, *, temperature: float | None = None) -> BaseChatModel:
    from langchain_gigachat import GigaChat

    if not settings.gigachat_auth_key:
        raise RuntimeError("GIGACHAT_AUTH_KEY must be set when LLM_PROVIDER=gigachat")
    kwargs = {
        "credentials": settings.gigachat_auth_key,
        "scope": settings.gigachat_scope,
        "model": model,
        "verify_ssl_certs": False,  # TODO: заменить на ca_bundle_file перед продакшеном
        "profanity_check": False,
        "timeout": 60,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    return GigaChat(**kwargs)


def _get_anthropic(model: str, *, temperature: float | None = None) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY must be set when LLM_PROVIDER=anthropic")
    return ChatAnthropic(
        api_key=settings.anthropic_api_key,
        model=model,
        temperature=temperature if temperature is not None else 0.2,
        timeout=60,
    )


def get_llm() -> BaseChatModel:
    """Основная модель: диалог, вызов инструментов."""
    if settings.llm_provider == "anthropic":
        return _get_anthropic(settings.anthropic_model)
    return _get_gigachat(settings.gigachat_model)


@lru_cache(maxsize=1)
def get_router_llm() -> BaseChatModel:
    """Лёгкая модель для роутера: одна классификация, нужна скорость."""
    if settings.llm_provider == "anthropic":
        return _get_anthropic(settings.anthropic_model, temperature=0.0)
    return _get_gigachat("GigaChat-2", temperature=0.0)

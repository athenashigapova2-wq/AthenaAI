"""Обёртка над LLM-провайдером.

Единственное место в проекте, которое знает, что модель — GigaChat.
Агенты работают с абстракцией BaseChatModel, поэтому смена провайдера
затрагивает только этот файл.
"""

from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_gigachat import GigaChat

from app.config import settings


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Основная модель: диалог, вызов инструментов."""
    return GigaChat(
        credentials=settings.gigachat_auth_key,
        scope=settings.gigachat_scope,
        model=settings.gigachat_model,
        verify_ssl_certs=False,   # TODO: заменить на ca_bundle_file перед продакшеном
        profanity_check=False,
        timeout=60,
    )


@lru_cache(maxsize=1)
def get_router_llm() -> BaseChatModel:
    """Лёгкая модель для роутера: одна классификация, нужна скорость."""
    return GigaChat(
        credentials=settings.gigachat_auth_key,
        scope=settings.gigachat_scope,
        model="GigaChat-2",
        verify_ssl_certs=False,
        temperature=0.0,   # классификация должна быть детерминированной
        timeout=30,
    )
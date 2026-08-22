"""Клиент Supabase для серверной части.

Использует service_role — он обходит RLS. Поэтому КАЖДЫЙ запрос
обязан фильтровать по user_id вручную. Забыть фильтр = утечка чужих данных.
"""

from threading import local

from supabase import Client, create_client

from app.config import settings

_thread_state = local()


def get_supabase() -> Client:
    """Return one Supabase client and HTTP connection pool per worker thread."""
    client = getattr(_thread_state, "client", None)
    if client is not None:
        return client

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY должны быть заданы в .env"
        )
    client = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
    _thread_state.client = client
    return client

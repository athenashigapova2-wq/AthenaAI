"""Клиент Supabase для серверной части.

Использует service_role — он обходит RLS. Поэтому КАЖДЫЙ запрос
обязан фильтровать по user_id вручную. Забыть фильтр = утечка чужих данных.
"""

from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY должны быть заданы в .env"
        )
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
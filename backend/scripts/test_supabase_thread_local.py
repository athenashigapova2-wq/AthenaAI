"""Offline checks for thread-local Supabase clients."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock, get_ident, local
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services import supabase as supabase_service  # noqa: E402


def assert_one_client_per_thread() -> None:
    worker_count = 4
    barrier = Barrier(worker_count)
    created_clients: list[tuple[int, object]] = []
    created_clients_lock = Lock()

    def create_fake_client(url: str, key: str) -> object:
        assert url == "https://project.supabase.co"
        assert key == "service-role-key"
        client = object()
        with created_clients_lock:
            created_clients.append((get_ident(), client))
        return client

    def get_client_twice() -> tuple[int, object, object]:
        barrier.wait(timeout=5)
        first = supabase_service.get_supabase()
        second = supabase_service.get_supabase()
        return get_ident(), first, second

    with (
        patch.object(settings, "supabase_url", "https://project.supabase.co"),
        patch.object(settings, "supabase_service_role_key", "service-role-key"),
        patch.object(supabase_service, "_thread_state", local()),
        patch.object(
            supabase_service,
            "create_client",
            side_effect=create_fake_client,
        ) as create_client,
        ThreadPoolExecutor(max_workers=worker_count) as executor,
    ):
        futures = [executor.submit(get_client_twice) for _ in range(worker_count)]
        results = [future.result(timeout=10) for future in futures]

    thread_ids = {thread_id for thread_id, _, _ in results}
    assert len(thread_ids) == worker_count
    assert all(first is second for _, first, second in results)
    assert len({id(first) for _, first, _ in results}) == worker_count
    assert create_client.call_count == worker_count
    assert {thread_id for thread_id, _ in created_clients} == thread_ids


def assert_missing_configuration_still_fails() -> None:
    with (
        patch.object(settings, "supabase_url", ""),
        patch.object(settings, "supabase_service_role_key", ""),
        patch.object(supabase_service, "_thread_state", local()),
        patch.object(supabase_service, "create_client") as create_client,
    ):
        try:
            supabase_service.get_supabase()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Missing Supabase configuration must fail")

    create_client.assert_not_called()


if __name__ == "__main__":
    assert_one_client_per_thread()
    assert_missing_configuration_still_fails()
    print("Supabase thread-local client checks passed")

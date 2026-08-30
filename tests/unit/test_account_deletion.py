from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from app.services import account_deletion

USER_ID = "11111111-1111-4111-8111-111111111111"


def test_auth_identity_is_deleted_only_after_runtime_and_storage_cleanup() -> None:
    events: list[str] = []
    client = MagicMock()
    client.auth.admin.delete_user.side_effect = lambda *_args, **_kwargs: events.append("auth")

    with (
        patch.object(account_deletion, "get_supabase", return_value=client),
        patch.object(
            account_deletion,
            "_scrub_runtime_state",
            side_effect=lambda _user_id: events.append("runtime") or 3,
        ),
        patch.object(
            account_deletion,
            "_delete_user_storage",
            side_effect=lambda _client, _user_id: events.append("storage") or 2,
        ),
    ):
        result = account_deletion.delete_account(USER_ID)

    assert events == ["runtime", "storage", "auth"]
    assert result.runtime_records_scrubbed == 3
    assert result.storage_objects_deleted == 2
    client.auth.admin.delete_user.assert_called_once_with(
        USER_ID,
        should_soft_delete=False,
    )


def test_storage_failure_preserves_auth_identity_for_retry() -> None:
    client = MagicMock()
    with (
        patch.object(account_deletion, "get_supabase", return_value=client),
        patch.object(account_deletion, "_scrub_runtime_state", return_value=0),
        patch.object(
            account_deletion,
            "_delete_user_storage",
            side_effect=account_deletion.AccountDeletionDependencyError("storage"),
        ),
        pytest.raises(account_deletion.AccountDeletionDependencyError),
    ):
        account_deletion.delete_account(USER_ID)

    client.auth.admin.delete_user.assert_not_called()


def test_storage_cleanup_recurses_under_user_prefix_and_batches_removal() -> None:
    bucket = MagicMock()
    bucket.list.side_effect = lambda prefix, _options: {
        USER_ID: [
            {"id": "file-1", "name": "receipt.pdf"},
            {"id": None, "name": "avatars"},
        ],
        f"{USER_ID}/avatars": [{"id": "file-2", "name": "profile.png"}],
    }.get(prefix, [])
    client = MagicMock()
    client.storage.list_buckets.return_value = [SimpleNamespace(id="private")]
    client.storage.from_.return_value = bucket

    deleted = account_deletion._delete_user_storage(client, USER_ID)

    assert deleted == 2
    assert bucket.remove.call_args_list == [
        call([f"{USER_ID}/receipt.pdf", f"{USER_ID}/avatars/profile.png"])
    ]


def test_user_owned_tables_and_traces_cascade_from_auth_deletion() -> None:
    migrations = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    schema = "\n".join(
        (migrations / name).read_text(encoding="utf-8")
        for name in (
            "0001_init.sql",
            "0002_agent_chat.sql",
            "0006_cycle_tracking.sql",
            "0011_agent_observability.sql",
            "0017_edge_llm_quota.sql",
        )
    )
    for table in (
        "profiles",
        "user_profiles",
        "meal_logs",
        "weight_logs",
        "workout_logs",
        "shopping_items",
        "agent_memory",
        "user_health_logs",
        "agent_conversations",
        "cycle_logs",
        "agent_runs",
        "agent_feedback",
        "edge_llm_usage",
    ):
        table_sql = schema.split(f"create table public.{table}", 1)[1].split(
            "create table public.", 1
        )[0]
        assert "references auth.users(id) on delete cascade" in table_sql

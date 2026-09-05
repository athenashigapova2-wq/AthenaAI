from copy import deepcopy
from unittest.mock import patch

import pytest
from langchain_core.tools import StructuredTool

from app.agents.common.tool_executor import _trace_safe_result
from app.services import write_confirmations
from app.tools.idempotent_writes import IdempotencyConflictError, insert_idempotently
from app.tools.write_context import require_idempotency_key


pytestmark = pytest.mark.unit


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def hset(self, *args, **kwargs):
        self.redis.hset(*args, **kwargs)
        return self

    def expire(self, *_args, **_kwargs):
        return self

    def execute(self):
        return []


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.values = {}

    def pipeline(self):
        return FakePipeline(self)

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})

    def hgetall(self, key):
        return deepcopy(self.hashes.get(key, {}))

    def hsetnx(self, key, field, value):
        record = self.hashes.setdefault(key, {})
        if field in record:
            return 0
        record[field] = value
        return 1

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def set(self, key, value, nx=False, ex=None):
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)
        self.hashes.pop(key, None)


def _stage(redis: FakeRedis, *, user_id: str = "user-1") -> dict:
    with patch("app.services.write_confirmations.redis_client", return_value=redis):
        return write_confirmations.stage_write_action(
            user_id=user_id,
            trace_id=None,
            conversation_id=None,
            locale="en",
            tool_name="log_meal",
            tool_args={"name": "Oats", "calories": 300},
        )["write_action"]


def test_confirmation_executes_once_and_replays_original_result() -> None:
    redis = FakeRedis()
    action = _stage(redis)
    executions = []

    def write_tool(name: str, calories: float) -> dict:
        executions.append((require_idempotency_key(), name, calories))
        return {"status": "ok", "logged": name, "idempotent_replay": False}

    tool = StructuredTool.from_function(
        func=write_tool,
        name="log_meal",
        description="write",
        metadata={"read_only": False, "requires_confirmation": True},
    )
    kwargs = {
        "action_id": action["action_id"],
        "user_id": "user-1",
        "confirmation_token": action["confirmation_token"],
        "idempotency_key": "meal:client-request-1",
    }
    with (
        patch("app.services.write_confirmations.redis_client", return_value=redis),
        patch("app.services.write_confirmations.build_tools", return_value=[tool]),
    ):
        first = write_confirmations.confirm_write_action(**kwargs)
        second = write_confirmations.confirm_write_action(**kwargs)

    assert first is not None and first["idempotent_replay"] is False
    assert second is not None and second["idempotent_replay"] is True
    assert executions == [("meal:client-request-1", "Oats", 300.0)]


def test_confirmation_is_owner_token_and_idempotency_scoped() -> None:
    redis = FakeRedis()
    first = _stage(redis)
    second = _stage(redis)
    tool = StructuredTool.from_function(
        func=lambda name, calories: {"status": "ok"},
        name="log_meal",
        description="write",
        metadata={"read_only": False, "requires_confirmation": True},
    )
    with (
        patch("app.services.write_confirmations.redis_client", return_value=redis),
        patch("app.services.write_confirmations.build_tools", return_value=[tool]),
    ):
        assert (
            write_confirmations.confirm_write_action(
                action_id=first["action_id"],
                user_id="other-user",
                confirmation_token=first["confirmation_token"],
                idempotency_key="meal:client-request-2",
            )
            is None
        )
        assert (
            write_confirmations.confirm_write_action(
                action_id=first["action_id"],
                user_id="user-1",
                confirmation_token="wrong-token-that-is-long-enough",
                idempotency_key="meal:client-request-2",
            )
            is None
        )
        write_confirmations.confirm_write_action(
            action_id=first["action_id"],
            user_id="user-1",
            confirmation_token=first["confirmation_token"],
            idempotency_key="meal:client-request-2",
        )
        with pytest.raises(write_confirmations.WriteActionConflictError):
            write_confirmations.confirm_write_action(
                action_id=second["action_id"],
                user_id="user-1",
                confirmation_token=second["confirmation_token"],
                idempotency_key="meal:client-request-2",
            )


def test_confirmation_token_never_enters_trace_payload() -> None:
    safe = _trace_safe_result(
        {
            "status": "confirmation_required",
            "write_action": {
                "action_id": "action",
                "confirmation_token": "secret",
                "tool_name": "log_meal",
                "preview": {"medical_condition": "sensitive"},
                "expires_at": "later",
            },
        }
    )
    assert "secret" not in str(safe)
    assert "sensitive" not in str(safe)


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, database, table):
        self.database = database
        self.table = table
        self.rows = deepcopy(database.rows)
        self.pending = None
        self.limit_count = None

    def select(self, *_args):
        return self

    def eq(self, field, value):
        self.rows = [row for row in self.rows if row.get(field) == value]
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def insert(self, payload):
        self.pending = deepcopy(payload)
        return self

    def execute(self):
        if self.pending is not None:
            self.database.rows.append(self.pending)
            return FakeResult([deepcopy(self.pending)])
        rows = self.rows[: self.limit_count] if self.limit_count else self.rows
        return FakeResult(rows)


class FakeDatabase:
    def __init__(self):
        self.rows = []

    def table(self, table):
        return FakeQuery(self, table)


def test_database_idempotency_replays_and_rejects_payload_drift() -> None:
    database = FakeDatabase()
    payload = {"user_id": "user-1", "name": "Oats", "calories": 300}

    _, first_replay = insert_idempotently(database, "meal_logs", payload, "meal:key-1")
    _, second_replay = insert_idempotently(database, "meal_logs", payload, "meal:key-1")

    assert first_replay is False
    assert second_replay is True
    assert len(database.rows) == 1
    with pytest.raises(IdempotencyConflictError):
        insert_idempotently(
            database,
            "meal_logs",
            {**payload, "calories": 999},
            "meal:key-1",
        )

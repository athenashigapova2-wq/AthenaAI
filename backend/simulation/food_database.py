"""Immutable food reference database for offline and live simulations."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


DEFAULT_FOOD_FIXTURE = Path(__file__).parent / "fixtures" / "test_food_nutrients.json"


@dataclass(frozen=True)
class TestFoodResult:
    data: list[dict[str, Any]]


class TestFoodQuery:
    """Small read-only subset of the Supabase query interface."""

    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = deepcopy(rows)
        self._limit: int | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "TestFoodQuery":
        return self

    def eq(self, field: str, value: Any) -> "TestFoodQuery":
        self._rows = [row for row in self._rows if row.get(field) == value]
        return self

    def limit(self, count: int) -> "TestFoodQuery":
        self._limit = count
        return self

    def execute(self) -> TestFoodResult:
        rows = self._rows[: self._limit] if self._limit is not None else self._rows
        return TestFoodResult(deepcopy(rows))

    def insert(self, *_args: Any, **_kwargs: Any) -> "TestFoodQuery":
        raise PermissionError("simulation food database is read-only")

    update = insert
    upsert = insert
    delete = insert


class TestFoodDatabase:
    """Auditable food catalogue that cannot access or mutate remote data."""

    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = deepcopy(rows)

    @classmethod
    def from_fixture(cls, path: Path = DEFAULT_FOOD_FIXTURE) -> "TestFoodDatabase":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(payload["foods"])

    def table(self, table_name: str) -> TestFoodQuery:
        if table_name != "food_nutrients":
            raise PermissionError(f"test food database does not expose {table_name}")
        return TestFoodQuery(self._rows)

    def rpc(self, function_name: str, params: dict[str, Any]) -> TestFoodQuery:
        if function_name != "search_food_nutrients":
            raise PermissionError(f"test food database does not expose {function_name}")
        query = str(params.get("search_term", "")).strip().lower()
        limit = int(params.get("match_limit", 5))
        ranked = sorted(
            self._rows,
            key=lambda row: SequenceMatcher(
                None, query, str(row.get("food_name", "")).lower()
            ).ratio(),
            reverse=True,
        )
        return TestFoodQuery(ranked[:limit])


def load_test_food_database() -> TestFoodDatabase:
    return TestFoodDatabase.from_fixture()

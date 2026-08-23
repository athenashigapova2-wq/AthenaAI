"""Repository-level checks for the ordered Supabase migration chain."""

from pathlib import Path
import re

import pytest


pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def test_migration_versions_are_unique_and_contiguous() -> None:
    files = sorted(MIGRATIONS.glob("*.sql"))
    assert files, "No Supabase migrations were found"

    matches = [MIGRATION_NAME.fullmatch(path.name) for path in files]
    assert all(matches), "Migration names must use NNNN_snake_case.sql"
    versions = [int(match.group(1)) for match in matches if match is not None]

    assert len(versions) == len(set(versions)), "Duplicate migration version"
    assert versions == list(range(1, len(versions) + 1)), (
        "Migration versions must be contiguous and start at 0001"
    )


@pytest.mark.parametrize("migration", sorted(MIGRATIONS.glob("*.sql")), ids=lambda p: p.name)
def test_migration_is_nonempty_sql(migration: Path) -> None:
    sql = migration.read_text(encoding="utf-8").strip()
    assert sql
    assert ";" in sql, f"{migration.name} contains no complete SQL statement"


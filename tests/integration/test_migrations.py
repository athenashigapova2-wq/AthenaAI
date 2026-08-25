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


def test_trace_privacy_migrations_define_lifecycle_and_classification() -> None:
    lifecycle = (MIGRATIONS / "0019_trace_payload_privacy.sql").read_text(encoding="utf-8")
    classification = (MIGRATIONS / "0021_trace_data_classification.sql").read_text(
        encoding="utf-8"
    )

    for required_policy in (
        "purge_expired_agent_trace_payloads",
        "purge_expired_agent_traces",
        "raw_payload_expires_at",
    ):
        assert required_policy in lifecycle
    for required_label in (
        "input_data_classification",
        "output_data_classification",
        "arg_data_classification",
        "result_data_classification",
    ):
        assert required_label in classification


def test_observability_2_migration_defines_trace_and_slo_metrics() -> None:
    sql = (MIGRATIONS / "0022_observability_2_slo_metrics.sql").read_text(
        encoding="utf-8"
    )

    for required_metric in (
        "queue_latency_ms",
        "provider_latency_ms",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "success_rate_percent",
        "total_tokens",
        "retry_rate_percent",
        "fallback_rate_percent",
        "rag_hit_rate_percent",
        "avg_eval_score",
        "agent_slo_metrics_hourly",
    ):
        assert required_metric in sql


def test_evaluation_experiment_migration_compares_quality_performance_and_cost() -> None:
    sql = (MIGRATIONS / "0023_evaluation_experiments.sql").read_text(encoding="utf-8")
    for required_field in (
        "experiment_id",
        "variant_id",
        "experiment_assignment_bucket",
        "experiment_config_hash",
        "avg_quality_score",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "avg_tokens_per_run",
        "estimated_cost_usd",
        "cost_coverage_percent",
        "agent_experiment_comparison",
    ):
        assert required_field in sql

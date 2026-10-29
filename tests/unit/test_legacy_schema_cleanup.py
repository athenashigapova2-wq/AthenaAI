from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "0028_remove_unused_legacy_tables.sql"
ROLLBACK = ROOT / "supabase" / "rollbacks" / "0028_restore_unused_legacy_tables.sql"


def test_cleanup_removes_only_verified_legacy_objects() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "drop function if exists public.consume_edge_llm_quota" in sql
    assert "drop table if exists public.edge_llm_usage" in sql
    assert "drop table if exists public.health_research" in sql
    assert "drop table if exists public.knowledge_documents" not in sql
    assert "cascade" not in sql


def test_cleanup_has_a_security_equivalent_manual_rollback() -> None:
    sql = ROLLBACK.read_text(encoding="utf-8").lower()

    assert "create table public.health_research" in sql
    assert "alter table public.health_research enable row level security" in sql
    assert 'create policy "health_research: read all authenticated"' in sql
    assert "create table public.edge_llm_usage" in sql
    assert "alter table public.edge_llm_usage enable row level security" in sql
    assert "revoke all on table public.edge_llm_usage from anon, authenticated" in sql
    assert "security definer" in sql
    assert "set search_path = public, pg_temp" in sql
    assert "to service_role" in sql

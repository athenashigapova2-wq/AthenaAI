-- Remove legacy database objects after verifying that they are empty and unused.
--
-- Audit summary:
--   * health_research had no runtime readers/writers and no rows.
--   * edge_llm_usage belonged to the retired Edge inference quota path and had no rows.
--   * knowledge_documents is intentionally retained: ingestion, knowledge_chunks and
--     match_knowledge_chunks still depend on it.
--
-- Rollback: supabase/rollbacks/0028_restore_unused_legacy_tables.sql

begin;

drop function if exists public.consume_edge_llm_quota(uuid, text, integer, integer);
drop table if exists public.edge_llm_usage;
drop table if exists public.health_research;

commit;

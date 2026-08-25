-- End-to-end trace correlation and production SLO aggregates.

alter table public.agent_runs
  add column job_id uuid,
  add column queue_latency_ms integer not null default 0
    check (queue_latency_ms >= 0),
  add column eval_score double precision
    check (eval_score is null or (eval_score >= 0 and eval_score <= 1)),
  add column rag_attempted boolean not null default false,
  add column rag_retrieved_chunk_count integer not null default 0
    check (rag_retrieved_chunk_count >= 0),
  add column rag_retrieval_latency_ms integer not null default 0
    check (rag_retrieval_latency_ms >= 0),
  add column rag_top_similarity double precision
    check (
      rag_top_similarity is null
      or (rag_top_similarity >= 0 and rag_top_similarity <= 1)
    ),
  add column rag_context_chars integer not null default 0
    check (rag_context_chars >= 0);

create unique index agent_runs_job_id_idx
  on public.agent_runs(job_id)
  where job_id is not null;

alter table public.agent_llm_calls
  add column provider_latency_ms integer
    check (provider_latency_ms is null or provider_latency_ms >= 0);

update public.agent_llm_calls
set provider_latency_ms = latency_ms
where provider_latency_ms is null and latency_ms is not null;

comment on column public.agent_runs.id is
  'Canonical trace_id propagated from HTTP through Redis, Celery, LangGraph, tools and LLM attempts.';
comment on column public.agent_runs.queue_latency_ms is
  'Elapsed milliseconds from accepted HTTP job creation to Celery worker start.';
comment on column public.agent_runs.eval_score is
  'Mean of bounded structured evaluation scores; no evaluator prompt or explanation.';
comment on column public.agent_llm_calls.provider_latency_ms is
  'Provider invocation latency only; excludes queueing and local orchestration.';

create or replace view public.agent_slo_metrics_hourly
with (security_invoker = true)
as
with llm_by_run as (
  select
    run_id,
    avg(provider_latency_ms) filter (where provider_latency_ms is not null)
      as provider_latency_ms,
    bool_or(is_fallback) as used_model_fallback
  from public.agent_llm_calls
  group by run_id
), run_facts as (
  select
    date_trunc('hour', r.created_at) as bucket,
    r.route,
    r.model_provider,
    r.model_name,
    r.status,
    r.latency_ms,
    r.queue_latency_ms,
    r.total_tokens,
    r.retry_count,
    r.resolution_mode = 'fallback'
      or r.routing_fallback_reason is not null
      or coalesce(l.used_model_fallback, false) as used_fallback,
    l.provider_latency_ms,
    r.rag_attempted,
    r.rag_retrieved_chunk_count,
    r.rag_retrieval_latency_ms,
    r.rag_top_similarity,
    r.rag_context_chars,
    r.eval_score
  from public.agent_runs r
  left join llm_by_run l on l.run_id = r.id
)
select
  bucket,
  route,
  model_provider,
  model_name,
  count(*)::bigint as run_count,
  100.0 * count(*) filter (where status = 'succeeded') / nullif(count(*), 0)
    as success_rate_percent,
  percentile_cont(0.50) within group (order by latency_ms)
    filter (where latency_ms is not null) as latency_p50_ms,
  percentile_cont(0.95) within group (order by latency_ms)
    filter (where latency_ms is not null) as latency_p95_ms,
  percentile_cont(0.99) within group (order by latency_ms)
    filter (where latency_ms is not null) as latency_p99_ms,
  sum(total_tokens)::bigint as total_tokens,
  avg(total_tokens) as avg_tokens_per_run,
  100.0 * count(*) filter (where retry_count > 0) / nullif(count(*), 0)
    as retry_rate_percent,
  100.0 * count(*) filter (where used_fallback) / nullif(count(*), 0)
    as fallback_rate_percent,
  percentile_cont(0.95) within group (order by queue_latency_ms)
    as queue_latency_p95_ms,
  percentile_cont(0.50) within group (order by provider_latency_ms)
    filter (where provider_latency_ms is not null) as provider_latency_p50_ms,
  percentile_cont(0.95) within group (order by provider_latency_ms)
    filter (where provider_latency_ms is not null) as provider_latency_p95_ms,
  percentile_cont(0.99) within group (order by provider_latency_ms)
    filter (where provider_latency_ms is not null) as provider_latency_p99_ms,
  100.0 * count(*) filter (
    where rag_attempted and rag_retrieved_chunk_count > 0
  ) / nullif(count(*) filter (where rag_attempted), 0) as rag_hit_rate_percent,
  avg(rag_retrieval_latency_ms) filter (where rag_attempted)
    as avg_rag_retrieval_latency_ms,
  avg(rag_retrieved_chunk_count) filter (where rag_attempted)
    as avg_rag_chunks,
  avg(rag_top_similarity) filter (where rag_top_similarity is not null)
    as avg_rag_top_similarity,
  avg(rag_context_chars) filter (where rag_attempted) as avg_rag_context_chars,
  avg(eval_score) filter (where eval_score is not null) as avg_eval_score
from run_facts
group by bucket, route, model_provider, model_name;

grant select on public.agent_slo_metrics_hourly to authenticated, service_role;

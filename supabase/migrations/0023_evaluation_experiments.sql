-- Reproducible server-side experiments with quality/performance/cost comparison.

alter table public.agent_runs
  add column experiment_id text,
  add column variant_id text,
  add column experiment_assignment_bucket integer
    check (
      experiment_assignment_bucket is null
      or (experiment_assignment_bucket >= 0 and experiment_assignment_bucket < 10000)
    ),
  add column experiment_config_hash text,
  add constraint agent_runs_experiment_pair_check
    check ((experiment_id is null) = (variant_id is null)),
  add constraint agent_runs_experiment_hash_check
    check (
      experiment_config_hash is null
      or experiment_config_hash ~ '^[0-9a-f]{64}$'
    );

create index agent_runs_experiment_variant_created_idx
  on public.agent_runs(experiment_id, variant_id, created_at desc)
  where experiment_id is not null;

alter table public.agent_llm_calls
  add column experiment_id text,
  add column variant_id text,
  add column input_cost_per_million_usd numeric(16, 6)
    check (input_cost_per_million_usd is null or input_cost_per_million_usd >= 0),
  add column output_cost_per_million_usd numeric(16, 6)
    check (output_cost_per_million_usd is null or output_cost_per_million_usd >= 0),
  add column estimated_cost_usd numeric(18, 9)
    check (estimated_cost_usd is null or estimated_cost_usd >= 0),
  add constraint agent_llm_calls_experiment_pair_check
    check ((experiment_id is null) = (variant_id is null));

create index agent_llm_calls_experiment_variant_created_idx
  on public.agent_llm_calls(experiment_id, variant_id, created_at desc)
  where experiment_id is not null;

comment on column public.agent_runs.experiment_assignment_bucket is
  'Stable 0..9999 hash bucket for the authenticated user assignment unit.';
comment on column public.agent_runs.experiment_config_hash is
  'SHA-256 of the canonical experiment definition used for this assignment.';
comment on column public.agent_llm_calls.estimated_cost_usd is
  'Estimate from the immutable per-attempt pricing snapshot and measured tokens.';

create or replace view public.agent_experiment_comparison
with (security_invoker = true)
as
with llm_by_run as (
  select
    run_id,
    sum(estimated_cost_usd) as estimated_cost_usd,
    count(*) filter (where estimated_cost_usd is not null) as costed_call_count,
    count(*) as llm_attempt_count,
    avg(provider_latency_ms) filter (where provider_latency_ms is not null)
      as provider_latency_ms,
    bool_or(is_fallback) as used_model_fallback
  from public.agent_llm_calls
  group by run_id
), facts as (
  select
    r.experiment_id,
    r.variant_id,
    r.experiment_config_hash,
    r.route,
    r.status,
    r.latency_ms,
    r.queue_latency_ms,
    r.total_tokens,
    r.retry_count,
    r.eval_score,
    l.estimated_cost_usd,
    l.costed_call_count,
    l.llm_attempt_count,
    l.provider_latency_ms,
    r.resolution_mode = 'fallback'
      or r.routing_fallback_reason is not null
      or coalesce(l.used_model_fallback, false) as used_fallback
  from public.agent_runs r
  left join llm_by_run l on l.run_id = r.id
  where r.experiment_id is not null
)
select
  experiment_id,
  variant_id,
  experiment_config_hash,
  route,
  count(*)::bigint as run_count,
  100.0 * count(*) filter (where status = 'succeeded') / nullif(count(*), 0)
    as success_rate_percent,
  avg(eval_score) filter (where eval_score is not null) as avg_quality_score,
  count(eval_score)::bigint as evaluated_run_count,
  percentile_cont(0.50) within group (order by latency_ms)
    filter (where latency_ms is not null) as latency_p50_ms,
  percentile_cont(0.95) within group (order by latency_ms)
    filter (where latency_ms is not null) as latency_p95_ms,
  percentile_cont(0.99) within group (order by latency_ms)
    filter (where latency_ms is not null) as latency_p99_ms,
  avg(total_tokens) as avg_tokens_per_run,
  sum(total_tokens)::bigint as total_tokens,
  sum(estimated_cost_usd) as estimated_cost_usd,
  avg(estimated_cost_usd) filter (where estimated_cost_usd is not null)
    as avg_estimated_cost_usd_per_run,
  100.0 * sum(costed_call_count) / nullif(sum(llm_attempt_count), 0)
    as cost_coverage_percent,
  100.0 * count(*) filter (where retry_count > 0) / nullif(count(*), 0)
    as retry_rate_percent,
  100.0 * count(*) filter (where used_fallback) / nullif(count(*), 0)
    as fallback_rate_percent,
  percentile_cont(0.95) within group (order by queue_latency_ms)
    as queue_latency_p95_ms,
  percentile_cont(0.95) within group (order by provider_latency_ms)
    filter (where provider_latency_ms is not null) as provider_latency_p95_ms
from facts
group by experiment_id, variant_id, experiment_config_hash, route;

grant select on public.agent_experiment_comparison to authenticated, service_role;

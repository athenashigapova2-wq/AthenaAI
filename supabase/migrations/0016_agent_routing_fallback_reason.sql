-- Make Router Agent degradation queryable instead of silently masking it.

alter table public.agent_runs
  add column routing_fallback_reason text;

create index agent_runs_routing_fallback_created_idx
  on public.agent_runs(created_at desc)
  where routing_fallback_reason is not null;

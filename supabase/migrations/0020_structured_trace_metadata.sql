-- Production-safe observability metadata. Content remains opt-in.

alter table public.agent_runs
  add column actor_id text,
  add column retry_count integer not null default 0 check (retry_count >= 0),
  add column evaluation_scores jsonb not null default '{}'::jsonb
    check (jsonb_typeof(evaluation_scores) = 'object');

update public.agent_runs
set actor_id = substring(
  encode(
    extensions.digest('athena-trace-actor:v1:' || user_id::text, 'sha256'),
    'hex'
  )
  from 1 for 32
)
where actor_id is null;

alter table public.agent_runs
  alter column actor_id set not null;

create index agent_runs_actor_created_idx
  on public.agent_runs(actor_id, created_at desc);

alter table public.agent_tool_calls
  add column arg_schema_version integer not null default 1
    check (arg_schema_version > 0),
  add column arg_count integer not null default 0
    check (arg_count >= 0),
  add column result_status text
    check (result_status in ('success', 'empty', 'error')),
  add column result_row_count integer
    check (result_row_count is null or result_row_count >= 0);

create or replace function public.refresh_agent_run_llm_metrics()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.agent_runs r set
    llm_call_count = m.call_count,
    retry_count = m.retry_count,
    token_accounted_call_count = m.accounted_call_count,
    input_tokens = m.input_tokens,
    output_tokens = m.output_tokens,
    cached_input_tokens = m.cached_input_tokens,
    total_tokens = m.total_tokens
  from (
    select
      count(*)::integer as call_count,
      greatest(count(*) - count(distinct invocation_id), 0)::integer as retry_count,
      count(*) filter (where token_usage_available)::integer as accounted_call_count,
      coalesce(sum(input_tokens), 0)::integer as input_tokens,
      coalesce(sum(output_tokens), 0)::integer as output_tokens,
      coalesce(sum(cached_input_tokens), 0)::integer as cached_input_tokens,
      coalesce(sum(total_tokens), 0)::integer as total_tokens
    from public.agent_llm_calls
    where run_id = new.run_id
  ) m
  where r.id = new.run_id;
  return new;
end;
$$;

comment on column public.agent_runs.actor_id is
  'Pseudonymous identifier for aggregate observability; user_id remains for ownership/RLS.';
comment on column public.agent_runs.evaluation_scores is
  'Numeric rubric scores only; evaluation prompts and explanations are not stored here.';
comment on column public.agent_tool_calls.arg_count is
  'Number of top-level arguments, never their values.';
comment on column public.agent_tool_calls.result_row_count is
  'Best-effort deterministic result cardinality without retaining result content.';

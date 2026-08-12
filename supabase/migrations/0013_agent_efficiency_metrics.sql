-- Per-call LLM accounting and run-level efficiency aggregates.

alter table public.agent_runs
  add column resolution_mode text not null default 'main_llm'
    check (resolution_mode in ('zero_llm', 'small_llm', 'main_llm', 'fallback')),
  add column baseline_version text not null default 'baseline-v1',
  add column llm_call_count integer not null default 0 check (llm_call_count >= 0),
  add column token_accounted_call_count integer not null default 0
    check (token_accounted_call_count >= 0),
  add column input_tokens integer not null default 0 check (input_tokens >= 0),
  add column output_tokens integer not null default 0 check (output_tokens >= 0),
  add column cached_input_tokens integer not null default 0 check (cached_input_tokens >= 0),
  add column total_tokens integer not null default 0 check (total_tokens >= 0),
  add column tool_step_count integer not null default 0 check (tool_step_count >= 0),
  add column tool_call_count integer not null default 0 check (tool_call_count >= 0);

alter table public.agent_tool_calls
  add column tool_step integer not null default 1 check (tool_step > 0);

create table public.agent_llm_calls (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.agent_runs(id) on delete cascade,
  node_name text not null,
  purpose text not null,
  model_provider text not null,
  model_name text not null,
  model_tier text not null check (model_tier in ('small', 'main')),
  status text not null default 'started' check (status in ('started', 'succeeded', 'failed')),
  token_usage_available boolean not null default false,
  input_tokens integer not null default 0 check (input_tokens >= 0),
  output_tokens integer not null default 0 check (output_tokens >= 0),
  cached_input_tokens integer not null default 0 check (cached_input_tokens >= 0),
  total_tokens integer not null default 0 check (total_tokens >= 0),
  latency_ms integer,
  error_message text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index agent_llm_calls_run_created_idx
  on public.agent_llm_calls(run_id, created_at);
create index agent_runs_baseline_created_idx
  on public.agent_runs(baseline_version, created_at desc);

alter table public.agent_llm_calls enable row level security;

create policy "agent_llm_calls: read via own run" on public.agent_llm_calls
  for select using (
    exists (
      select 1 from public.agent_runs r
      where r.id = agent_llm_calls.run_id and r.user_id = auth.uid()
    )
  );

create or replace function public.refresh_agent_run_llm_metrics()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.agent_runs r set
    llm_call_count = m.call_count,
    token_accounted_call_count = m.accounted_call_count,
    input_tokens = m.input_tokens,
    output_tokens = m.output_tokens,
    cached_input_tokens = m.cached_input_tokens,
    total_tokens = m.total_tokens
  from (
    select
      count(*)::integer as call_count,
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

create trigger agent_llm_calls_refresh_run_metrics
after insert or update on public.agent_llm_calls
for each row execute function public.refresh_agent_run_llm_metrics();

create or replace function public.refresh_agent_run_tool_metrics()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.agent_runs r set
    tool_call_count = m.call_count,
    tool_step_count = m.step_count
  from (
    select
      count(*)::integer as call_count,
      coalesce(max(tool_step), 0)::integer as step_count
    from public.agent_tool_calls
    where run_id = new.run_id
  ) m
  where r.id = new.run_id;
  return new;
end;
$$;

create trigger agent_tool_calls_refresh_run_metrics
after insert or update on public.agent_tool_calls
for each row execute function public.refresh_agent_run_tool_metrics();

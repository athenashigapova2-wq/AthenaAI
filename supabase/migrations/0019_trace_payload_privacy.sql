-- Formal agent trace lifecycle: redaction -> retention -> export -> deletion.

alter table public.agent_runs
  alter column input_text drop not null,
  add column payload_mode text not null default 'legacy'
    check (payload_mode in ('legacy', 'full', 'redacted', 'none')),
  add column redaction_version text,
  add column raw_payload_expires_at timestamptz;

create index agent_runs_payload_expiry_idx
  on public.agent_runs(raw_payload_expires_at)
  where raw_payload_expires_at is not null;

comment on column public.agent_runs.payload_mode is
  'Whether this run stores full, redacted, no, or pre-policy legacy payloads.';
comment on column public.agent_runs.raw_payload_expires_at is
  'Deadline after which prompt, response, tool payloads, and error text are purged.';

create or replace function public.purge_expired_agent_trace_payloads()
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  affected bigint;
begin
  update public.agent_tool_calls as tool_call
  set tool_args = '{}'::jsonb,
      tool_result = '{}'::jsonb,
      error_message = null
  where exists (
    select 1
    from public.agent_runs as run
    where run.id = tool_call.run_id
      and run.raw_payload_expires_at <= now()
  );

  update public.agent_llm_calls as llm_call
  set error_message = null
  where exists (
    select 1
    from public.agent_runs as run
    where run.id = llm_call.run_id
      and run.raw_payload_expires_at <= now()
  );

  update public.agent_runs
  set input_text = null,
      output_text = null,
      error_message = null,
      payload_mode = 'none',
      raw_payload_expires_at = null
  where raw_payload_expires_at <= now();

  get diagnostics affected = row_count;
  return affected;
end;
$$;

create or replace function public.purge_expired_agent_traces(p_before timestamptz)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  affected bigint;
begin
  delete from public.agent_runs
  where created_at < p_before;
  get diagnostics affected = row_count;
  return affected;
end;
$$;

revoke all on function public.purge_expired_agent_trace_payloads() from public, anon, authenticated;
revoke all on function public.purge_expired_agent_traces(timestamptz) from public, anon, authenticated;
grant execute on function public.purge_expired_agent_trace_payloads() to service_role;
grant execute on function public.purge_expired_agent_traces(timestamptz) to service_role;
